"""Immutable ledger events: drafts, the hash chain, and typed constructors.

An ``EventDraft`` is what a caller proposes; a ``LedgerEvent`` is the same content plus the
sequence number and hash links the ledger assigns. Content is canonical JSON of primitives only
(Decimals as strings), so hashes are stable across runs, machines and Python versions.

``event_id`` is the idempotency key. Callers derive it from the real-world thing that happened
(an order fill, a corporate action and holder), never from a counter or a clock, so retrying a
step after a crash appends nothing new.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from the_reef.market.instruments import settlement_event_id

GENESIS_HASH = "0" * 64


class EventKind(str, Enum):
    EPOCH_OPENED = "EPOCH_OPENED"
    EPOCH_CLOSED = "EPOCH_CLOSED"
    SLEEVE_CREATED = "SLEEVE_CREATED"
    SLEEVE_FUNDED = "SLEEVE_FUNDED"  # signed: fund cash <-> sleeve cash
    FILL = "FILL"
    STOP_UPDATED = "STOP_UPDATED"
    CORPORATE_ACTION_SETTLED = "CORPORATE_ACTION_SETTLED"
    ORDER_QUEUED = "ORDER_QUEUED"  # a decision waiting for its fill session's open
    ORDER_REJECTED = "ORDER_REJECTED"  # refused at decision time or at fill time
    SESSION_MARKED = "SESSION_MARKED"  # end-of-session valuation, verified against the books
    SESSION_CLOSED = "SESSION_CLOSED"  # every step of the session is done; the next may start


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


def freeze(obj: Any) -> Any:
    """Deep, defensive copy that cannot be mutated: dict -> read-only mapping, list -> tuple."""
    if isinstance(obj, Mapping):
        return MappingProxyType({str(k): freeze(v) for k, v in obj.items()})
    if isinstance(obj, (list, tuple)):
        return tuple(freeze(v) for v in obj)
    return obj


def thaw(obj: Any) -> Any:
    if isinstance(obj, Mapping):
        return {k: thaw(v) for k, v in obj.items()}
    if isinstance(obj, tuple):
        return [thaw(v) for v in obj]
    return obj


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def derive_id(*parts: str) -> str:
    """Deterministic idempotency key from the identity of the thing that happened."""
    return digest("|".join(parts))[:32]


@dataclass(frozen=True)
class EventDraft:
    event_id: str
    epoch_id: str
    kind: EventKind
    occurred_at: datetime  # when it happened in the simulated/real world; timezone-aware
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if not self.event_id:
            raise ValueError("event_id is required")
        # Copy and freeze: a caller's retained dict (or a nested list) can no longer change an event.
        object.__setattr__(self, "payload", freeze(self.payload))

    def content(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "epoch_id": self.epoch_id,
            "kind": self.kind.value,
            "occurred_at": self.occurred_at.astimezone(timezone.utc).isoformat(),
            "payload": thaw(self.payload),
        }

    @property
    def fingerprint(self) -> str:
        """Content hash. The same ``event_id`` with a different fingerprint is a conflict."""
        return digest(canonical(self.content()))


@dataclass(frozen=True)
class LedgerEvent:
    seq: int
    prev_hash: str
    hash: str
    draft: EventDraft

    @staticmethod
    def link(seq: int, prev_hash: str, draft: EventDraft) -> "LedgerEvent":
        return LedgerEvent(seq, prev_hash, chain_hash(seq, prev_hash, draft), draft)

    def verify(self) -> bool:
        return self.hash == chain_hash(self.seq, self.prev_hash, self.draft)


def chain_hash(seq: int, prev_hash: str, draft: EventDraft) -> str:
    return digest(f"{seq}|{prev_hash}|{draft.fingerprint}")


# --- typed constructors ---------------------------------------------------------------------
# Money and prices travel as strings; shares as ints.

def _d(x: Decimal) -> str:
    return format(x, "f")


def epoch_opened(epoch_id: str, at: datetime, initial_cash: Decimal) -> EventDraft:
    return EventDraft(derive_id("epoch_opened", epoch_id), epoch_id, EventKind.EPOCH_OPENED, at,
                      {"initial_cash": _d(initial_cash)})


def epoch_closed(epoch_id: str, at: datetime, reason: str = "") -> EventDraft:
    return EventDraft(derive_id("epoch_closed", epoch_id), epoch_id, EventKind.EPOCH_CLOSED, at, {"reason": reason})


def sleeve_created(epoch_id: str, at: datetime, sleeve_id: str) -> EventDraft:
    return EventDraft(derive_id("sleeve_created", epoch_id, sleeve_id), epoch_id, EventKind.SLEEVE_CREATED, at,
                      {"sleeve_id": sleeve_id})


def sleeve_funded(epoch_id: str, at: datetime, sleeve_id: str, amount: Decimal, ref: str) -> EventDraft:
    """``amount`` > 0 moves fund cash into the sleeve; < 0 returns it. ``ref`` makes the key unique
    per allocation decision (for example the allocator run id)."""
    return EventDraft(derive_id("sleeve_funded", epoch_id, sleeve_id, ref), epoch_id, EventKind.SLEEVE_FUNDED, at,
                      {"sleeve_id": sleeve_id, "amount": _d(amount), "ref": ref})


def fill_id(epoch_id: str, sleeve_id: str, order_id: str) -> str:
    """One order fills once per sleeve: the id comes from the order, not from the fill."""
    return derive_id("fill", epoch_id, sleeve_id, order_id)


def fill(
    epoch_id: str, at: datetime, *, sleeve_id: str, order_id: str, symbol: str, side: Side,
    shares: int, price: Decimal, session_day: date, stop_price: Decimal | None = None,
) -> EventDraft:
    payload: dict[str, Any] = {
        "sleeve_id": sleeve_id, "order_id": order_id, "symbol": symbol, "side": side.value,
        "shares": shares, "price": _d(price), "session_day": session_day.isoformat(),
    }
    if stop_price is not None:
        payload["stop_price"] = _d(stop_price)
    return EventDraft(fill_id(epoch_id, sleeve_id, order_id), epoch_id, EventKind.FILL, at, payload)


def stop_updated(epoch_id: str, at: datetime, sleeve_id: str, symbol: str, stop_price: Decimal, ref: str) -> EventDraft:
    return EventDraft(derive_id("stop_updated", epoch_id, sleeve_id, symbol, ref), epoch_id, EventKind.STOP_UPDATED, at,
                      {"sleeve_id": sleeve_id, "symbol": symbol, "stop_price": _d(stop_price), "ref": ref})


def corporate_action_settled(
    epoch_id: str, at: datetime, *, sleeve_id: str, symbol: str, shares: int, cash: Decimal,
    action_id: str, effective: date,
) -> EventDraft:
    """Unique per epoch, sleeve and action: the id is derived here, never supplied, and the ledger
    re-derives it on apply. It equals ``CashOut.event_id`` from ``settlements_due(scope=epoch_id)``."""
    return EventDraft(settlement_event_id(action_id, sleeve_id, epoch_id), epoch_id, EventKind.CORPORATE_ACTION_SETTLED, at, {
        "sleeve_id": sleeve_id, "symbol": symbol, "shares": shares, "cash": _d(cash),
        "action_id": action_id, "effective": effective.isoformat(),
    })


def order_key(sleeve_id: str, order_id: str) -> str:
    return f"{sleeve_id}:{order_id}"


def order_queued(
    epoch_id: str, at: datetime, *, sleeve_id: str, order_id: str, symbol: str, intent: str,
    requested_shares: int | None, stop_price: Decimal | None, fill_session: date, ref_price: Decimal,
    sector: str | None, rationale: str = "",
) -> EventDraft:
    return EventDraft(derive_id("order_queued", epoch_id, sleeve_id, order_id), epoch_id, EventKind.ORDER_QUEUED, at, {
        "sleeve_id": sleeve_id, "order_id": order_id, "symbol": symbol, "intent": intent,
        "requested_shares": requested_shares, "stop_price": None if stop_price is None else _d(stop_price),
        "fill_session": fill_session.isoformat(), "ref_price": _d(ref_price), "sector": sector, "rationale": rationale,
        "decided_at": at.isoformat(),
    })


def order_rejected(
    epoch_id: str, at: datetime, *, sleeve_id: str, order_id: str, stage: str, code: str, detail: str = "",
    symbol: str = "",
) -> EventDraft:
    """``stage`` is DECISION (never queued) or FILL (queued, then refused at the open)."""
    return EventDraft(derive_id("order_rejected", epoch_id, sleeve_id, order_id, stage), epoch_id,
                      EventKind.ORDER_REJECTED, at, {
        "sleeve_id": sleeve_id, "order_id": order_id, "stage": stage, "code": code, "detail": detail, "symbol": symbol,
    })


def session_marked(
    epoch_id: str, at: datetime, *, session_day: date, marks: Mapping[str, Decimal], unmarked: list[str],
    nav: Decimal, sleeve_nav: Mapping[str, Decimal],
) -> EventDraft:
    return EventDraft(derive_id("session_marked", epoch_id, session_day.isoformat()), epoch_id,
                      EventKind.SESSION_MARKED, at, {
        "session_day": session_day.isoformat(), "marks": {k: _d(v) for k, v in sorted(marks.items())},
        "unmarked": sorted(unmarked), "nav": _d(nav), "sleeve_nav": {k: _d(v) for k, v in sorted(sleeve_nav.items())},
    })


def session_closed(epoch_id: str, at: datetime, session_day: date) -> EventDraft:
    return EventDraft(derive_id("session_closed", epoch_id, session_day.isoformat()), epoch_id,
                      EventKind.SESSION_CLOSED, at, {"session_day": session_day.isoformat()})
