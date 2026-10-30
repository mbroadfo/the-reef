"""Ledger state and the pure ``apply`` step. Replaying the same events always gives the same state.

Structure: one fund per epoch. The fund holds unallocated cash plus independent virtual sleeves
(one per shark/pod). A sleeve has its own cash and positions; nothing moves between sleeves
except through fund cash (``SLEEVE_FUNDED``). Positions never carry across epochs.

Conservation, checked by ``check_invariants`` and the tests:
    unallocated + sum(sleeve cash) + sum(position cost) == initial cash + sum(realized P&L)
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from enum import Enum
from typing import Mapping

from the_reef.market.instruments import settlement_event_id
from the_reef.ledger.events import GENESIS_HASH, EventDraft, EventKind, LedgerEvent, Side, canonical, digest

D = Decimal
ZERO = D("0")
_COST_QUANT = D("0.00000001")


class LedgerError(ValueError):
    """An event that would corrupt the books. Nothing is appended when this is raised."""


class ConflictError(LedgerError):
    """The same event_id arrived with different content."""


@dataclass(frozen=True)
class Position:
    shares: int
    cost: Decimal  # total cost basis of the shares held
    stop_price: Decimal | None = None

    @property
    def avg_cost(self) -> Decimal:
        return self.cost / self.shares


@dataclass(frozen=True)
class SleeveState:
    cash: Decimal = ZERO
    positions: Mapping[str, Position] = field(default_factory=dict)
    realized_pnl: Decimal = ZERO

    def __post_init__(self) -> None:
        object.__setattr__(self, "positions", MappingProxyType(dict(self.positions)))

    def shares_of(self, symbol: str) -> int:
        p = self.positions.get(symbol)
        return p.shares if p else 0


class OrderStatus(str, Enum):
    QUEUED = "QUEUED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class OrderRecord:
    sleeve_id: str
    order_id: str
    symbol: str
    intent: str
    requested_shares: int | None
    stop_price: Decimal | None
    fill_session: str  # ISO date; empty for decision-stage rejections
    ref_price: Decimal | None
    sector: str | None
    status: OrderStatus
    decided_at: str = ""


@dataclass(frozen=True)
class EpochState:
    epoch_id: str
    initial_cash: Decimal
    unallocated: Decimal
    sleeves: Mapping[str, SleeveState] = field(default_factory=dict)
    closed: bool = False
    orders: Mapping[str, OrderRecord] = field(default_factory=dict)  # key: sleeve_id:order_id
    marks: Mapping[str, Decimal] = field(default_factory=dict)  # session ISO date -> verified fund NAV
    last_completed: str = ""  # ISO date of the last fully finished session
    last_mark_prices: Mapping[str, Decimal] = field(default_factory=dict)  # official closes of the last marked session
    last_unmarked: frozenset[str] = frozenset()  # held names that session could not mark

    def __post_init__(self) -> None:
        object.__setattr__(self, "sleeves", MappingProxyType(dict(self.sleeves)))
        object.__setattr__(self, "orders", MappingProxyType(dict(self.orders)))
        object.__setattr__(self, "marks", MappingProxyType(dict(self.marks)))
        object.__setattr__(self, "last_mark_prices", MappingProxyType(dict(self.last_mark_prices)))

    def pending_orders(self) -> list[OrderRecord]:
        return [o for _, o in sorted(self.orders.items()) if o.status is OrderStatus.QUEUED]

    @property
    def last_marked(self) -> str | None:
        return max(self.marks) if self.marks else None

    @property
    def high_water_mark(self) -> Decimal:
        return max([self.initial_cash, *self.marks.values()])

    @property
    def realized_pnl(self) -> Decimal:
        return sum((s.realized_pnl for s in self.sleeves.values()), ZERO)

    @property
    def cash(self) -> Decimal:
        return self.unallocated + sum((s.cash for s in self.sleeves.values()), ZERO)

    def holdings(self, sleeve_id: str) -> dict[str, int]:
        return {sym: p.shares for sym, p in self.sleeves[sleeve_id].positions.items()}


@dataclass(frozen=True)
class LedgerState:
    epochs: Mapping[str, EpochState] = field(default_factory=dict)
    active_epoch: str | None = None
    seen: Mapping[str, str] = field(default_factory=dict)  # event_id -> fingerprint
    last_seq: int = 0
    last_at: datetime | None = None
    head_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "epochs", MappingProxyType(dict(self.epochs)))
        object.__setattr__(self, "seen", MappingProxyType(dict(self.seen)))

    def epoch(self, epoch_id: str | None = None) -> EpochState:
        key = epoch_id or self.active_epoch
        if key is None or key not in self.epochs:
            raise LedgerError("no such epoch")
        return self.epochs[key]

    def digest(self) -> str:
        """Hash of the whole books. Equal digests mean equal state; used by replay tests."""
        body = {
            eid: {
                "initial": str(e.initial_cash), "unallocated": str(e.unallocated), "closed": e.closed,
                "marks": {d: str(v) for d, v in sorted(e.marks.items())}, "completed": e.last_completed,
                "last_marks": {k: str(v) for k, v in sorted(e.last_mark_prices.items())},
                "last_unmarked": sorted(e.last_unmarked),
                "orders": {k: [o.status.value, o.symbol, o.intent, o.requested_shares, o.fill_session]
                           for k, o in sorted(e.orders.items())},
                "sleeves": {
                    sid: {
                        "cash": str(s.cash), "realized": str(s.realized_pnl),
                        "positions": {
                            sym: [p.shares, str(p.cost), None if p.stop_price is None else str(p.stop_price)]
                            for sym, p in sorted(s.positions.items())
                        },
                    }
                    for sid, s in sorted(e.sleeves.items())
                },
            }
            for eid, e in sorted(self.epochs.items())
        }
        return digest(canonical({"epochs": body, "active": self.active_epoch, "seq": self.last_seq}))


# --- apply ------------------------------------------------------------------------------------

def _dec(payload: Mapping[str, object], key: str) -> Decimal:
    try:
        return D(str(payload[key]))
    except Exception as exc:  # noqa: BLE001
        raise LedgerError(f"bad or missing decimal {key!r}") from exc


def _int(payload: Mapping[str, object], key: str) -> int:
    v = payload.get(key)
    if isinstance(v, bool) or not isinstance(v, int):
        raise LedgerError(f"{key!r} must be an integer (whole shares only)")
    return v


def _str(payload: Mapping[str, object], key: str) -> str:
    v = payload.get(key)
    if not isinstance(v, str) or not v:
        raise LedgerError(f"missing {key!r}")
    return v


def validate(state: LedgerState, draft: EventDraft) -> EpochState | None:
    """Return the epoch the event targets (None for EPOCH_OPENED) or raise."""
    if state.last_at is not None and draft.occurred_at < state.last_at:
        raise LedgerError("occurred_at precedes the previous event")
    if draft.kind is EventKind.EPOCH_OPENED:
        if draft.epoch_id in state.epochs:
            raise LedgerError(f"epoch {draft.epoch_id} already exists")
        if state.active_epoch is not None:
            raise LedgerError("an epoch is already active; close it first (one Reef, one active epoch)")
        return None
    if draft.epoch_id not in state.epochs:
        raise LedgerError(f"unknown epoch {draft.epoch_id}")
    ep = state.epochs[draft.epoch_id]
    if ep.closed:
        raise LedgerError(f"epoch {draft.epoch_id} is closed")
    return ep


def apply(state: LedgerState, ev: LedgerEvent) -> LedgerState:
    """Pure transition. Raises ``LedgerError`` for anything that would break an invariant."""
    draft = ev.draft
    if ev.seq != state.last_seq + 1:
        raise LedgerError(f"sequence gap: expected {state.last_seq + 1}, got {ev.seq}")
    if ev.prev_hash != (state.head_hash or GENESIS_HASH):
        raise LedgerError("hash chain broken")
    if not ev.verify():
        raise LedgerError("event hash does not match its content")
    ep = validate(state, draft)
    p = draft.payload
    epochs = dict(state.epochs)
    active = state.active_epoch

    if draft.kind is EventKind.EPOCH_OPENED:
        cash = _dec(p, "initial_cash")
        if cash <= 0:
            raise LedgerError("initial cash must be positive")
        epochs[draft.epoch_id] = EpochState(draft.epoch_id, cash, cash)
        active = draft.epoch_id
    else:
        assert ep is not None
        if draft.kind is EventKind.EPOCH_CLOSED:
            epochs[ep.epoch_id] = replace(ep, closed=True)
            active = None if active == ep.epoch_id else active
        else:
            epochs[ep.epoch_id] = _apply_in_epoch(ep, draft)

    seen = dict(state.seen)
    seen[draft.event_id] = draft.fingerprint
    return LedgerState(epochs, active, seen, ev.seq, draft.occurred_at, ev.hash)


def _sleeve(ep: EpochState, sleeve_id: str) -> SleeveState:
    if sleeve_id not in ep.sleeves:
        raise LedgerError(f"unknown sleeve {sleeve_id}")
    return ep.sleeves[sleeve_id]


def _put(ep: EpochState, sleeve_id: str, sleeve: SleeveState, **epoch_changes: object) -> EpochState:
    sleeves = dict(ep.sleeves)
    sleeves[sleeve_id] = sleeve
    return replace(ep, sleeves=sleeves, **epoch_changes)  # type: ignore[arg-type]


def _apply_in_epoch(ep: EpochState, draft: EventDraft) -> EpochState:
    p = draft.payload
    kind = draft.kind

    if kind is EventKind.SLEEVE_CREATED:
        sid = _str(p, "sleeve_id")
        if sid in ep.sleeves:
            raise LedgerError(f"sleeve {sid} exists")
        return _put(ep, sid, SleeveState())

    if kind is EventKind.SESSION_MARKED:
        return _apply_mark(ep, draft)
    if kind is EventKind.SESSION_CLOSED:
        day = _str(p, "session_day")
        if day != ep.last_marked:
            raise LedgerError(f"session {day} cannot close before it is marked (last marked {ep.last_marked})")
        if day <= ep.last_completed:
            raise LedgerError(f"session {day} is already closed")
        return replace(ep, last_completed=day)

    sid = _str(p, "sleeve_id")
    sl = _sleeve(ep, sid)

    if kind is EventKind.ORDER_QUEUED:
        oid = _str(p, "order_id")
        key = f"{sid}:{oid}"
        if key in ep.orders:
            raise LedgerError(f"order {key} already exists")
        intent = _str(p, "intent")
        if intent not in ("open", "add", "reduce", "close"):
            raise LedgerError(f"bad order intent {intent!r}")
        req = p.get("requested_shares")
        if req is not None and (isinstance(req, bool) or not isinstance(req, int) or req <= 0):
            raise LedgerError("requested_shares must be a positive integer or null")
        stop = None if p.get("stop_price") is None else _dec(p, "stop_price")
        rec = OrderRecord(sid, oid, _str(p, "symbol"), intent, req, stop, _str(p, "fill_session"),
                          _dec(p, "ref_price"), p.get("sector") if isinstance(p.get("sector"), str) else None,  # type: ignore[arg-type]
                          OrderStatus.QUEUED, str(p.get("decided_at", "")))
        return replace(ep, orders={**ep.orders, key: rec})

    if kind is EventKind.ORDER_REJECTED:
        oid = _str(p, "order_id")
        key = f"{sid}:{oid}"
        stage = _str(p, "stage")
        existing = ep.orders.get(key)
        if stage == "FILL":
            if existing is None or existing.status is not OrderStatus.QUEUED:
                raise LedgerError(f"order {key} is not pending; it cannot be rejected at fill")
            return replace(ep, orders={**ep.orders, key: replace(existing, status=OrderStatus.REJECTED)})
        if stage == "DECISION":
            if existing is not None:
                raise LedgerError(f"order {key} already exists")
            rec = OrderRecord(sid, oid, str(p.get("symbol", "")), "", None, None, "", None, None, OrderStatus.REJECTED)
            return replace(ep, orders={**ep.orders, key: rec})
        raise LedgerError(f"bad rejection stage {stage!r}")

    if kind is EventKind.SLEEVE_FUNDED:
        amount = _dec(p, "amount")
        if amount == 0:
            raise LedgerError("zero funding")
        if amount > 0 and amount > ep.unallocated:
            raise LedgerError("funding exceeds unallocated fund cash")
        if amount < 0 and -amount > sl.cash:
            raise LedgerError("defunding exceeds sleeve cash")
        return _put(ep, sid, replace(sl, cash=sl.cash + amount), unallocated=ep.unallocated - amount)

    symbol = _str(p, "symbol")

    if kind is EventKind.FILL:
        side = Side(_str(p, "side"))
        shares = _int(p, "shares")
        price = _dec(p, "price")
        if shares <= 0 or price <= 0:
            raise LedgerError("fill needs positive whole shares and price")
        pos = sl.positions.get(symbol)
        positions = dict(sl.positions)
        orders = ep.orders
        okey = f"{sid}:{p['order_id']}" if "order_id" in p else ""
        if okey in ep.orders:
            rec = ep.orders[okey]
            if rec.status is not OrderStatus.QUEUED:
                raise LedgerError(f"order {okey} is {rec.status.value}; it cannot fill")
            if rec.symbol != symbol or (rec.requested_shares is not None and shares > rec.requested_shares):
                raise LedgerError(f"fill does not match queued order {okey}")
            orders = {**ep.orders, okey: replace(rec, status=OrderStatus.FILLED)}
        if side is Side.BUY:
            cost = price * shares
            if cost > sl.cash:
                raise LedgerError(f"buy of {cost} exceeds sleeve cash {sl.cash}")
            stop = _dec(p, "stop_price") if "stop_price" in p else (pos.stop_price if pos else None)
            if stop is not None and stop >= price:
                raise LedgerError("stop must be below the fill price")
            positions[symbol] = Position((pos.shares if pos else 0) + shares, (pos.cost if pos else ZERO) + cost, stop)
            return _put(ep, sid, replace(sl, cash=sl.cash - cost, positions=positions), orders=orders)
        if pos is None or shares > pos.shares:
            raise LedgerError(f"sell of {shares} exceeds {pos.shares if pos else 0} held (no shorting)")
        removed = pos.cost if shares == pos.shares else (pos.cost * shares / pos.shares).quantize(_COST_QUANT, ROUND_HALF_EVEN)
        proceeds = price * shares
        if shares == pos.shares:
            del positions[symbol]
        else:
            positions[symbol] = Position(pos.shares - shares, pos.cost - removed, pos.stop_price)
        return _put(ep, sid, replace(sl, cash=sl.cash + proceeds, positions=positions,
                                     realized_pnl=sl.realized_pnl + proceeds - removed), orders=orders)

    if kind is EventKind.STOP_UPDATED:
        pos = sl.positions.get(symbol)
        if pos is None:
            raise LedgerError(f"no position in {symbol} to attach a stop to")
        stop = _dec(p, "stop_price")
        if stop <= 0:
            raise LedgerError("stop must be positive")
        positions = dict(sl.positions)
        positions[symbol] = replace(pos, stop_price=stop)
        return _put(ep, sid, replace(sl, positions=positions))

    if kind is EventKind.CORPORATE_ACTION_SETTLED:
        shares = _int(p, "shares")
        cash = _dec(p, "cash")
        if draft.event_id != settlement_event_id(_str(p, "action_id"), sid, ep.epoch_id):
            raise LedgerError("settlement event_id must be derived from epoch, sleeve and action")
        pos = sl.positions.get(symbol)
        if pos is None or pos.shares != shares:
            raise LedgerError(f"settlement of {shares} {symbol} does not match the {pos.shares if pos else 0} held")
        if cash < 0:
            raise LedgerError("settlement cash cannot be negative")
        positions = dict(sl.positions)
        del positions[symbol]
        return _put(ep, sid, replace(sl, cash=sl.cash + cash, positions=positions,
                                     realized_pnl=sl.realized_pnl + cash - pos.cost))

    raise LedgerError(f"unhandled event kind {kind}")


def valuation(ep: EpochState, marks: Mapping[str, Decimal], unmarked: set[str] | frozenset[str]) -> tuple[Decimal, dict[str, Decimal]]:
    """Fund NAV and per-sleeve NAV. An unmarked holding is carried at cost and the caller must
    treat the book as untrusted (E-6). Every held symbol must be marked or declared unmarked."""
    total = ep.unallocated
    sleeve_nav: dict[str, Decimal] = {}
    for sid, sl in ep.sleeves.items():
        nav = sl.cash
        for sym, pos in sl.positions.items():
            if sym in marks:
                nav += marks[sym] * pos.shares
            elif sym in unmarked:
                nav += pos.cost
            else:
                raise LedgerError(f"held symbol {sym} is neither marked nor declared unmarked")
        sleeve_nav[sid] = nav
        total += nav
    return total, sleeve_nav


def _apply_mark(ep: EpochState, draft: EventDraft) -> EpochState:
    """Verify an end-of-session valuation against the books, then record the fund NAV.

    Every held symbol must be either marked or declared unmarked (valued at cost, which makes the
    book untrusted for the caller); the stated NAVs must equal the recomputation exactly.
    """
    p = draft.payload
    day = _str(p, "session_day")
    if ep.last_marked is not None and day <= ep.last_marked:
        raise LedgerError(f"session {day} is not after the last marked session {ep.last_marked}")
    if ep.last_marked is not None and ep.last_completed != ep.last_marked:
        raise LedgerError(f"session {ep.last_marked} is not closed; it must finish before {day} is marked")
    marks = {k: D(str(v)) for k, v in dict(p.get("marks", {})).items()}  # type: ignore[call-overload]
    unmarked = set(p.get("unmarked", ()))  # type: ignore[call-overload]
    if any(v <= 0 for v in marks.values()):
        raise LedgerError("marks must be positive")
    total, sleeve_nav = valuation(ep, marks, unmarked)
    if D(str(p["nav"])) != total:
        raise LedgerError(f"stated NAV {p['nav']} does not match the books {total}")
    stated = {k: D(str(v)) for k, v in dict(p.get("sleeve_nav", {})).items()}  # type: ignore[call-overload]
    if stated != sleeve_nav:
        raise LedgerError("stated sleeve NAVs do not match the books")
    return replace(ep, marks={**ep.marks, day: total}, last_mark_prices=marks, last_unmarked=frozenset(unmarked))


def replay(events: list[LedgerEvent]) -> LedgerState:
    state = LedgerState()
    for ev in events:
        state = apply(state, ev)
    return state


def check_invariants(state: LedgerState) -> None:
    """Raise ``LedgerError`` if the books do not balance. Cheap enough to run after every test step."""
    for ep in state.epochs.values():
        invested = sum((p.cost for s in ep.sleeves.values() for p in s.positions.values()), ZERO)
        if ep.cash + invested != ep.initial_cash + ep.realized_pnl:
            raise LedgerError(f"epoch {ep.epoch_id} does not balance")
        if ep.unallocated < 0 or any(s.cash < 0 for s in ep.sleeves.values()):
            raise LedgerError("negative cash")
        if any(p.shares <= 0 for s in ep.sleeves.values() for p in s.positions.values()):
            raise LedgerError("non-positive position")
