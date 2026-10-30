"""Ledger state and the pure ``apply`` step. Replaying the same events always gives the same state.

Structure: one fund per epoch. The fund holds unallocated cash plus independent virtual sleeves
(one per shark/pod). A sleeve has its own cash and positions; nothing moves between sleeves
except through fund cash (``SLEEVE_FUNDED``). Positions never carry across epochs.

Conservation, checked by ``check_invariants`` and the tests:
    unallocated + sum(sleeve cash) + sum(position cost) == initial cash + sum(realized P&L)
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Mapping

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

    def shares_of(self, symbol: str) -> int:
        p = self.positions.get(symbol)
        return p.shares if p else 0


@dataclass(frozen=True)
class EpochState:
    epoch_id: str
    initial_cash: Decimal
    unallocated: Decimal
    sleeves: Mapping[str, SleeveState] = field(default_factory=dict)
    closed: bool = False

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

    sid = _str(p, "sleeve_id")
    sl = _sleeve(ep, sid)

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
        if side is Side.BUY:
            cost = price * shares
            if cost > sl.cash:
                raise LedgerError(f"buy of {cost} exceeds sleeve cash {sl.cash}")
            stop = _dec(p, "stop_price") if "stop_price" in p else (pos.stop_price if pos else None)
            if stop is not None and stop >= price:
                raise LedgerError("stop must be below the fill price")
            positions[symbol] = Position((pos.shares if pos else 0) + shares, (pos.cost if pos else ZERO) + cost, stop)
            return _put(ep, sid, replace(sl, cash=sl.cash - cost, positions=positions))
        if pos is None or shares > pos.shares:
            raise LedgerError(f"sell of {shares} exceeds {pos.shares if pos else 0} held (no shorting)")
        removed = pos.cost if shares == pos.shares else (pos.cost * shares / pos.shares).quantize(_COST_QUANT, ROUND_HALF_EVEN)
        proceeds = price * shares
        if shares == pos.shares:
            del positions[symbol]
        else:
            positions[symbol] = Position(pos.shares - shares, pos.cost - removed, pos.stop_price)
        return _put(ep, sid, replace(sl, cash=sl.cash + proceeds, positions=positions,
                                     realized_pnl=sl.realized_pnl + proceeds - removed))

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
