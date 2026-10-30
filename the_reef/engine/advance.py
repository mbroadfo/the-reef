"""``advance(session)``: the one loop that runs the shared engine for a trading session.

Everything the Reef knows lives in the ledger; ``advance`` is a function of the ledger, the
injected data ports and the session. It reads no clock, calls no model and touches no database.
It is idempotent: running a session again, or finishing one that was interrupted, appends only
what is missing and ends in exactly the state an uninterrupted run would have produced.

Order of work for session T (times are the event times recorded in the ledger):

  open(T)   1. cash out held names whose acquisition took effect (point-in-time corporate actions)
            2. resolve orders queued at an earlier close against T's official open, exits first:
               tradability re-checked, open print validated, Risk Engine sizes at the open price
            3. resting stops: a gap through the stop fills at the open, an intraday touch at the stop
  close(T)  4. mark every holding at the official close and record the verified valuation
  close+1m  5. strategies review holdings (raise stops, propose exits) and propose entries from
               bars that closed by now; D0 caps size; the gate and a risk pre-check admit or refuse;
               admitted orders are queued for the next valid open

Decisions are made at the close and filled at the next valid open (decision D6).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Sequence

from the_reef.allocation.d0 import D0Config, allocate, sleeve_targets
from the_reef.execution.gate import GatePorts, OrderIntent, QueuedOrder, fill_at_open, queue_order
from the_reef.ledger import events as ev
from the_reef.ledger.events import EventDraft, Side
from the_reef.ledger.ledger import AppendResult, Ledger
from the_reef.ledger.state import EpochState, OrderRecord, valuation
from the_reef.ledger.views import fund_view
from the_reef.market.bars import BarSource, last_closes
from the_reef.market.calendar import MarketCalendar
from the_reef.market.instruments import CorporateActionSource, InstrumentMaster, Intent
from the_reef.market.quotes import MarkStatus, mark_close
from the_reef.risk.engine import PortfolioView, evaluate_entry
from the_reef.risk.limits import RiskLimits
from the_reef.strategy.base import HoldingView, Proposal, Strategy, StrategyContext

D = Decimal
HISTORY_BARS = 120
DECISION_DELAY = timedelta(minutes=1)


class EngineError(RuntimeError):
    pass


@dataclass(frozen=True)
class SleeveSpec:
    sleeve_id: str
    strategy: Strategy


@dataclass(frozen=True)
class EngineDeps:
    epoch_id: str
    calendar: MarketCalendar
    instruments: InstrumentMaster
    actions: CorporateActionSource
    bars: BarSource
    limits: RiskLimits
    d0: D0Config
    sleeves: Sequence[SleeveSpec]
    universe: Sequence[str]
    initial_cash: Decimal = D("10000")

    @property
    def ports(self) -> GatePorts:
        return GatePorts(self.calendar, self.instruments, self.actions, self.limits)


class NoteKind(str, Enum):
    CASH_OUT = "CASH_OUT"
    FILL = "FILL"
    FILL_REJECTED = "FILL_REJECTED"
    STOP_GAP = "STOP_GAP"
    STOP_TOUCH = "STOP_TOUCH"
    STOP_UNCHECKED = "STOP_UNCHECKED"
    MARKED = "MARKED"
    STOP_RAISED = "STOP_RAISED"
    QUEUED = "QUEUED"
    DECISION_REJECTED = "DECISION_REJECTED"


@dataclass(frozen=True)
class Note:
    kind: NoteKind
    sleeve_id: str = ""
    symbol: str = ""
    detail: str = ""


@dataclass
class AdvanceReport:
    session_day: date
    notes: list[Note] = field(default_factory=list)
    appended: int = 0
    duplicates: int = 0
    nav: Decimal | None = None

    def add(self, kind: NoteKind, sleeve_id: str = "", symbol: str = "", detail: str = "") -> None:
        self.notes.append(Note(kind, sleeve_id, symbol, detail))


def _emit(ledger: Ledger, draft: EventDraft, report: AdvanceReport) -> AppendResult:
    result = ledger.append(draft)
    if result is AppendResult.APPENDED:
        report.appended += 1
    else:
        report.duplicates += 1
    return result


# --- epoch start --------------------------------------------------------------------------------

def bootstrap(ledger: Ledger, deps: EngineDeps, at: datetime) -> AdvanceReport:
    """Open the epoch all-cash and fund each sleeve by D0's fixed weights. Idempotent."""
    report = AdvanceReport(date.min)
    _emit(ledger, ev.epoch_opened(deps.epoch_id, at, deps.initial_cash), report)
    targets = sleeve_targets(deps.initial_cash, deps.d0)
    for spec in deps.sleeves:
        _emit(ledger, ev.sleeve_created(deps.epoch_id, at, spec.sleeve_id), report)
        amount = targets.get(spec.sleeve_id, D("0"))
        if amount > 0:
            _emit(ledger, ev.sleeve_funded(deps.epoch_id, at, spec.sleeve_id, amount, ref="d0-initial"), report)
    return report


# --- helpers ------------------------------------------------------------------------------------

def _sector(deps: EngineDeps, symbol: str, as_of: datetime) -> str | None:
    rec = deps.instruments.get(symbol, as_of)
    return rec.sector if rec else None


def _prior_nav(ep: EpochState, before_day: date) -> Decimal:
    earlier = [d for d in ep.marks if d < before_day.isoformat()]
    return ep.marks[max(earlier)] if earlier else ep.initial_cash


def _risk_view(ep: EpochState, deps: EngineDeps, as_of: datetime, session_day: date) -> PortfolioView:
    symbols = sorted({s for sl in ep.sleeves.values() for s in sl.positions})
    marks = last_closes(deps.bars, symbols, as_of)
    sectors = {s: _sector(deps, s, as_of) for s in symbols}
    return fund_view(ep, marks, sectors, prior_close_nav=_prior_nav(ep, session_day), high_water_mark=ep.high_water_mark)


def _reject_code(d) -> str:  # GateDecision
    parts = [d.code.value]
    if d.tradability is not None and d.tradability.value != "OK":
        parts.append(d.tradability.value)
    if d.risk is not None and d.risk.reasons:
        parts.extend(r.value for r in d.risk.reasons)
    if d.quote_issues:
        parts.extend(q.value for q in d.quote_issues)
    return ":".join(parts)


# --- the loop -----------------------------------------------------------------------------------

def advance(ledger: Ledger, deps: EngineDeps, day: date) -> AdvanceReport:
    session = deps.calendar.session(day)
    if session is None:
        raise EngineError(f"{day} is not a trading session")
    ep = ledger.state.epoch(deps.epoch_id)
    if ledger.state.active_epoch != deps.epoch_id:
        raise EngineError(f"epoch {deps.epoch_id} is not the active epoch")
    last = ep.last_marked
    if last is not None:
        if day.isoformat() < last:
            raise EngineError(f"{day} is before the last started session {last}")
        if day.isoformat() > last:
            if ep.last_completed != last:
                raise EngineError(f"session {last} is not complete; resume it before advancing to {day}")
            if deps.calendar.next_session(date.fromisoformat(last)).day != day:
                raise EngineError(f"{day} skips a session after {last}; advance one session at a time")
    report = AdvanceReport(day)
    open_at, close_at = session.open, session.close
    decide_at = close_at + DECISION_DELAY
    sleeve_ids = [s.sleeve_id for s in deps.sleeves]

    if ep.last_completed == day.isoformat():
        return report  # nothing left to do
    # The mark is written last of steps 1-4, so a session that already has one finished them.
    # Re-running them afterwards would be wrong: stops raised at this close are not the stops
    # that were resting during the session. The "closed" event, written after step 5, says the
    # whole session is done; between the two, only step 5 may be re-run.
    if ep.last_marked != day.isoformat():
        # 1. corporate actions
        for r, sid in _settle(ledger, deps, sleeve_ids, day, open_at):
            report.add(NoteKind.CASH_OUT, sid, detail=r)
        # 2. queued orders meet today's open
        _resolve_orders(ledger, deps, day, report)
        # 3. resting stops
        _run_stops(ledger, deps, day, decide_at, report)
        # 4. mark to the close
        _mark(ledger, deps, day, report)
    # 5. decisions for the next open
    _decide(ledger, deps, day, decide_at, report)
    _emit(ledger, ev.session_closed(deps.epoch_id, decide_at, day), report)
    return report


def next_session_to_advance(ledger: Ledger, deps: EngineDeps, first_session: date) -> date:
    """Where to (re)start: an unfinished session first, otherwise the session after the last one."""
    ep = ledger.state.epoch(deps.epoch_id)
    if ep.last_marked is None:
        return first_session
    last = date.fromisoformat(ep.last_marked)
    return last if ep.last_completed != ep.last_marked else deps.calendar.next_session(last).day


def _settle(ledger: Ledger, deps: EngineDeps, sleeve_ids: list[str], day: date, at: datetime) -> list[tuple[str, str]]:
    before = set(ledger.state.seen)
    ledger.settle_corporate_actions(sleeve_ids, deps.actions, day, at)
    out = []
    for e in ledger.store.read_all():
        if e.draft.event_id not in before and e.draft.kind is ev.EventKind.CORPORATE_ACTION_SETTLED:
            p = e.draft.payload
            out.append((f"{p['shares']} {p['symbol']} cashed out for {p['cash']}", str(p["sleeve_id"])))
    return out


def _resolve_orders(ledger: Ledger, deps: EngineDeps, day: date, report: AdvanceReport) -> None:
    session = deps.calendar.session(day)
    assert session is not None
    pending = ledger.state.epoch(deps.epoch_id).pending_orders()
    # Exits first so their cash is available to entries at the same open.
    pending.sort(key=lambda o: (Intent(o.intent).adds_exposure, o.sleeve_id, o.order_id))
    for o in pending:
        if o.fill_session < day.isoformat():
            _emit(ledger, ev.order_rejected(deps.epoch_id, session.open, sleeve_id=o.sleeve_id, order_id=o.order_id,
                                            stage="FILL", code="MISSED_SESSION", symbol=o.symbol), report)
            report.add(NoteKind.FILL_REJECTED, o.sleeve_id, o.symbol, "MISSED_SESSION")
            continue
        if o.fill_session != day.isoformat():
            continue
        _resolve_one(ledger, deps, o, day, report)


def _resolve_one(ledger: Ledger, deps: EngineDeps, o: OrderRecord, day: date, report: AdvanceReport) -> None:
    session = deps.calendar.session(day)
    assert session is not None
    ep = ledger.state.epoch(deps.epoch_id)
    intent = Intent(o.intent)
    order = OrderIntent(o.sleeve_id, o.symbol, intent, datetime.fromisoformat(o.decided_at), o.ref_price or D("0"),
                        o.stop_price, o.sector, o.requested_shares)
    queued = QueuedOrder(order, o.symbol, day, session.open)
    open_print = deps.bars.official_open(o.symbol, session)
    view = _risk_view(ep, deps, session.open, day)
    d = fill_at_open(deps.ports, queued, open_print, view, ep.sleeves[o.sleeve_id].cash)
    if not d.accepted or open_print is None or open_print.price is None:
        code = _reject_code(d)
        _emit(ledger, ev.order_rejected(deps.epoch_id, session.open, sleeve_id=o.sleeve_id, order_id=o.order_id,
                                        stage="FILL", code=code, detail=d.detail, symbol=o.symbol), report)
        report.add(NoteKind.FILL_REJECTED, o.sleeve_id, o.symbol, code)
        return
    side = Side.BUY if intent.adds_exposure else Side.SELL
    _emit(ledger, ev.fill(deps.epoch_id, session.open, sleeve_id=o.sleeve_id, order_id=o.order_id, symbol=o.symbol,
                          side=side, shares=d.shares, price=open_print.price, session_day=day,
                          stop_price=o.stop_price if intent.adds_exposure else None), report)
    clamps = ",".join(c.rule.value for c in (d.risk.clamps if d.risk else ()))
    report.add(NoteKind.FILL, o.sleeve_id, o.symbol,
               f"{side.value} {d.shares} @ {open_print.price} (open){' clamped by ' + clamps if clamps else ''}")


def _run_stops(ledger: Ledger, deps: EngineDeps, day: date, as_of: datetime, report: AdvanceReport) -> None:
    session = deps.calendar.session(day)
    assert session is not None
    ep = ledger.state.epoch(deps.epoch_id)
    for sid, sl in sorted(ep.sleeves.items()):
        for sym, pos in sorted(sl.positions.items()):
            if pos.stop_price is None:
                continue
            bar = deps.bars.bar(sym, day, as_of)
            if bar is None:
                report.add(NoteKind.STOP_UNCHECKED, sid, sym, "no bar for the session; stop not evaluated")
                continue
            if bar.open <= pos.stop_price:  # gapped through the stop: filled at the open, not at the stop
                price, at, kind = bar.open, session.open, NoteKind.STOP_GAP
            elif bar.low <= pos.stop_price:  # traded through intraday: filled at the stop
                price, at, kind = pos.stop_price, session.close, NoteKind.STOP_TOUCH
            else:
                continue
            _emit(ledger, ev.fill(deps.epoch_id, at, sleeve_id=sid, order_id=f"stop:{sym}:{day.isoformat()}", symbol=sym,
                                  side=Side.SELL, shares=pos.shares, price=price, session_day=day), report)
            report.add(kind, sid, sym, f"SELL {pos.shares} @ {price} (stop {pos.stop_price}, open {bar.open}, low {bar.low})")


def _mark(ledger: Ledger, deps: EngineDeps, day: date, report: AdvanceReport) -> None:
    session = deps.calendar.session(day)
    assert session is not None
    ep = ledger.state.epoch(deps.epoch_id)
    held = sorted({s for sl in ep.sleeves.values() for s in sl.positions})
    marks: dict[str, Decimal] = {}
    unmarked: list[str] = []
    for sym in held:
        m = mark_close(deps.bars.official_close(sym, session), symbol=sym, session=session)
        if m.status is MarkStatus.MARKED and m.price is not None:
            marks[sym] = m.price
        else:
            unmarked.append(sym)
    nav, sleeve_nav = valuation(ep, marks, frozenset(unmarked))
    _emit(ledger, ev.session_marked(deps.epoch_id, session.close, session_day=day, marks=marks, unmarked=unmarked,
                                    nav=nav, sleeve_nav=sleeve_nav), report)
    report.nav = nav
    report.add(NoteKind.MARKED, detail=f"NAV {nav}" + (f"; UNMARKED {','.join(unmarked)}" if unmarked else ""))


def _decide(ledger: Ledger, deps: EngineDeps, day: date, decide_at: datetime, report: AdvanceReport) -> None:
    for spec in deps.sleeves:
        ep = ledger.state.epoch(deps.epoch_id)
        sl = ep.sleeves[spec.sleeve_id]
        # Orders from earlier closes only: re-running today's decisions must see the same inputs.
        blocked = frozenset(o.symbol for o in ep.pending_orders()
                            if o.sleeve_id == spec.sleeve_id and o.decided_at < decide_at.isoformat())
        symbols = sorted(set(deps.universe) | set(sl.positions))
        ctx = StrategyContext(
            session_day=day, as_of=decide_at,
            bars={s: deps.bars.history(s, decide_at, HISTORY_BARS) for s in symbols},
            holdings={s: HoldingView(p.shares, p.avg_cost, p.stop_price) for s, p in sl.positions.items()},
            blocked=blocked,
        )
        review = spec.strategy.review(ctx)
        for sym, new_stop in sorted(review.new_stops.items()):
            pos = sl.positions.get(sym)
            if pos is not None and (pos.stop_price is None or new_stop > pos.stop_price):
                _emit(ledger, ev.stop_updated(deps.epoch_id, decide_at, spec.sleeve_id, sym, new_stop, ref=day.isoformat()), report)
                report.add(NoteKind.STOP_RAISED, spec.sleeve_id, sym, f"stop {pos.stop_price} -> {new_stop}")
        for exit_prop in review.exits:
            if exit_prop.symbol in blocked:
                continue
            _queue(ledger, deps, spec, exit_prop, sl.positions[exit_prop.symbol].shares, day, decide_at, report)
        props = [p for p in spec.strategy.propose(ctx) if p.symbol not in blocked]
        for alloc in allocate(props, sl.cash, deps.d0):
            _queue(ledger, deps, spec, alloc.proposal, alloc.ceiling_shares, day, decide_at, report)


def _queue(ledger: Ledger, deps: EngineDeps, spec: SleeveSpec, prop: Proposal, shares: int, day: date,
           decide_at: datetime, report: AdvanceReport) -> None:
    ep = ledger.state.epoch(deps.epoch_id)
    sector = _sector(deps, prop.symbol, decide_at)
    order_id = f"{spec.strategy.strategy_id}:{day.isoformat()}:{prop.symbol}:{prop.intent.value}"

    def refuse(code: str, detail: str) -> None:
        _emit(ledger, ev.order_rejected(deps.epoch_id, decide_at, sleeve_id=spec.sleeve_id, order_id=order_id,
                                        stage="DECISION", code=code, detail=detail, symbol=prop.symbol), report)
        report.add(NoteKind.DECISION_REJECTED, spec.sleeve_id, prop.symbol, f"{code}: {detail}")

    if shares <= 0:
        return refuse("SIZE_ZERO", "allocator ceiling is zero shares")
    intent = OrderIntent(spec.sleeve_id, prop.symbol, prop.intent, decide_at, prop.ref_price, prop.stop_price, sector, shares)
    gate = queue_order(deps.ports, intent)
    if not gate.accepted or gate.queued is None:
        return refuse(_reject_code(gate), gate.detail)
    if prop.intent.adds_exposure:
        assert prop.stop_price is not None
        view = _risk_view(ep, deps, decide_at, day)
        risk = evaluate_entry(symbol=prop.symbol, sector=sector, ref_price=prop.ref_price, stop_price=prop.stop_price,
                              sleeve_cash=ep.sleeves[spec.sleeve_id].cash, portfolio=view, limits=deps.limits,
                              requested_shares=shares)
        if not risk.approved:
            return refuse(":".join(["RISK_REJECTED", *(r.value for r in risk.reasons)]), "pre-trade risk check at the close")
    _emit(ledger, ev.order_queued(deps.epoch_id, decide_at, sleeve_id=spec.sleeve_id, order_id=order_id,
                                  symbol=prop.symbol, intent=prop.intent.value, requested_shares=shares,
                                  stop_price=prop.stop_price, fill_session=gate.queued.fill_session,
                                  ref_price=prop.ref_price, sector=sector,
                                  rationale=f"[{spec.strategy.strategy_id}@{spec.strategy.spec_hash}] {prop.rationale}"), report)
    report.add(NoteKind.QUEUED, spec.sleeve_id, prop.symbol,
               f"{prop.intent.value} up to {shares} sh for {gate.queued.fill_session}; {prop.rationale}")
