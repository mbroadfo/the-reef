"""Replay Hunter on the shared engine over a historical window and measure it from the ledger.

Nothing here trades or decides: it builds the deps, calls ``advance`` once per session, and reads
results from the ledger events. Benchmarks are computed from the same point-in-time bars.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

from the_reef.allocation.d0 import D0Config
from the_reef.backtest.history import HistoricalBarSource
from the_reef.backtest.universe import BENCHMARK, SECTOR_OF, UNIVERSE
from the_reef.engine.advance import EngineDeps, NoteKind, SleeveSpec, advance, bootstrap
from the_reef.execution.costs import ExecutionCosts
from the_reef.ledger.events import EventKind
from the_reef.ledger.ledger import Ledger
from the_reef.market.calendar import MarketCalendar
from the_reef.market.instruments import (
    InstrumentRecord,
    InstrumentStatus,
    StaticCorporateActions,
    StaticInstrumentMaster,
)
from the_reef.performance.metrics import (
    buy_and_hold,
    fund_nav_series,
    funded_capital,
    max_drawdown,
    round_trips,
    sleeve_nav_series,
    total_return,
)
from the_reef.risk.limits import RiskLimits
from the_reef.strategy.hunter import Hunter

D = Decimal
SLEEVE = "hunter"
WEIGHT = D("0.40")


def instrument_master(bars: HistoricalBarSource) -> StaticInstrumentMaster:
    """Static facts: first trade date = first cached bar; sector = today's classification."""
    recs = []
    for sym, q in bars.quality.per_symbol.items():
        if q.first is not None:
            recs.append(InstrumentRecord(sym, "NYSE", InstrumentStatus.ACTIVE, q.first, None, SECTOR_OF.get(sym),
                                         "static-research-universe", datetime(2000, 1, 1, tzinfo=timezone.utc)))
    return StaticInstrumentMaster(recs)


def sessions_between(cal: MarketCalendar, start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if cal.session(d) is not None:
            out.append(d)
        d += timedelta(days=1)
    return out


def equal_weight_series(bars: HistoricalBarSource, cal: MarketCalendar, symbols: Sequence[str], capital: Decimal,
                        days: Sequence[date]) -> list[tuple[str, Decimal]]:
    """Equal-dollar basket of the universe, fractional units, bought at the first open, never traded.

    A survivorship yardstick, not a tradable benchmark: it holds only names that are still listed.
    Marked at each close; a missing close carries the last known one.
    """
    first = cal.session(days[0])
    held = {}
    live = [s for s in symbols if (q := bars.official_open(s, first)) is not None and q.price]  # type: ignore[arg-type]
    for s in live:
        held[s] = (capital / len(live)) / bars.official_open(s, first).price  # type: ignore[union-attr]
    out = []
    for d in days:
        close = cal.session(d).close  # type: ignore[union-attr]
        nav = D("0")
        for s, units in held.items():
            h = bars.history(s, close, 1)
            nav += units * h[-1].close
        out.append((d.isoformat(), nav))
    return out


@dataclass
class WindowResult:
    label: str
    start: date
    end: date
    sessions: int
    sleeve_return: Decimal
    fund_return: Decimal
    sleeve_max_dd: Decimal
    fund_max_dd: Decimal
    spy_return: Decimal
    spy_max_dd: Decimal
    basket_return: Decimal  # equal-dollar buy-and-hold of the (survivor) universe
    basket_max_dd: Decimal
    avg_exposure: Decimal  # mean of invested / sleeve NAV across sessions
    round_trips: int
    wins: int
    stop_exits: int
    gap_stops: int
    turnover: Decimal  # buy notional / funded sleeve capital
    entries_rejected: int
    fills_rejected: int
    unmarked_sessions: int
    pause_share: Decimal = D("0")  # share of sessions the fund sat 10%+ under its high-water mark (entries paused)
    exposure: list[Decimal] = field(default_factory=list)


def run_window(label: str, cal: MarketCalendar, bars: HistoricalBarSource, start: date, end: date,
               costs: ExecutionCosts = ExecutionCosts(), universe: Sequence[str] = UNIVERSE) -> WindowResult:
    days = sessions_between(cal, start, end)
    deps = EngineDeps(
        epoch_id=f"replay-{label}", calendar=cal, instruments=instrument_master(bars), actions=StaticCorporateActions([]),
        bars=bars, limits=RiskLimits(), d0=D0Config({SLEEVE: WEIGHT}, max_new_per_session=2),
        sleeves=[SleeveSpec(SLEEVE, Hunter())], universe=tuple(universe), costs=costs,
    )
    led = Ledger()
    bootstrap(led, deps, cal.session(days[0]).open - timedelta(hours=1))  # type: ignore[union-attr]
    exposure: list[Decimal] = []
    gap_stops = unmarked = 0
    for day in days:
        rep = advance(led, deps, day)
        gap_stops += sum(1 for n in rep.notes if n.kind is NoteKind.STOP_GAP)
        ep = led.state.epoch(deps.epoch_id)
        sl = ep.sleeves[SLEEVE]
        if ep.last_unmarked:
            unmarked += 1
        invested = sum(((ep.last_mark_prices.get(s) or p.avg_cost) * p.shares for s, p in sl.positions.items()), D("0"))
        nav = sl.cash + invested
        exposure.append(invested / nav if nav > 0 else D("0"))
    events = list(led.store.read_all())
    eid = deps.epoch_id
    cap = funded_capital(events, eid, SLEEVE)
    s_series, f_series = sleeve_nav_series(events, eid, SLEEVE), fund_nav_series(events, eid)
    first, last = days[0], days[-1]
    spy = buy_and_hold(bars, cal, [BENCHMARK], cap, first, last)
    basket = equal_weight_series(bars, cal, universe, cap, days)
    hwm, paused = deps.initial_cash, 0
    for _, v in f_series:
        hwm = max(hwm, v)
        paused += (hwm - v) / hwm >= deps.limits.drawdown_pause_pct
    trips = round_trips(events, eid, SLEEVE)
    buys = sum((D(str(e.draft.payload["price"])) * int(e.draft.payload["shares"]) for e in events
                if e.draft.kind is EventKind.FILL and e.draft.payload["side"] == "BUY"), D("0"))
    rej = [e.draft.payload for e in events if e.draft.kind is EventKind.ORDER_REJECTED]
    return WindowResult(
        label, first, last, len(days), total_return(s_series, cap), total_return(f_series, deps.initial_cash),
        max_drawdown(s_series, cap), max_drawdown(f_series, deps.initial_cash),
        total_return(spy.series, cap), max_drawdown(spy.series, cap), total_return(basket, cap),
        max_drawdown(basket, cap), sum(exposure, D("0")) / len(exposure), len(trips),
        sum(1 for t in trips if t.pnl > 0), sum(1 for t in trips if t.exit_reason == "stop"), gap_stops,
        buys / cap if cap else D("0"), sum(1 for r in rej if r["stage"] == "DECISION"),
        sum(1 for r in rej if r["stage"] == "FILL"), unmarked, D(paused) / len(f_series), exposure=exposure,
    )
