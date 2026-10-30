"""The ledger: an append-only event store plus the state it implies.

``EventStore`` is the persistence port. Slice 2 ships only the in-memory implementation; a
database adapter must satisfy the contract below. Nothing here writes to a database.

``Ledger.append`` is the single write path:
  * duplicate ``event_id`` with the same content  -> ``AppendResult.DUPLICATE``, nothing written
  * duplicate ``event_id`` with different content -> ``ConflictError``
  * an event that would break an invariant        -> ``LedgerError``, nothing written
  * otherwise it is chained, applied, stored      -> ``AppendResult.APPENDED``

What the hash chain does and does not prove
-------------------------------------------
Each event's hash covers its sequence number, the previous hash and its content. That detects an
edited event, a dropped or reordered event in the middle, and an inserted event. It CANNOT detect
truncation of the tail: the first N events of a valid chain are themselves a valid chain. Nor can
it detect a whole history rewritten and re-chained consistently from the start. Only a head
(``Checkpoint``: sequence and hash) preserved somewhere the store's writer cannot alter can.

Persistent-store contract (for the future database adapter)
-----------------------------------------------------------
1. Append-only: no update or delete of events; unique index on ``seq`` and on ``event_id``.
2. Appends are atomic and strictly sequential (``seq`` = previous + 1, ``prev_hash`` = previous hash).
3. After each successful append the new ``Checkpoint`` is recorded OUTSIDE the event collection,
   with separate credentials or in a separate system (for example the daily report and a
   write-once object), and the load path passes the last preserved checkpoint to
   ``Ledger(store, expected=checkpoint)``.
4. On load the ledger replays the whole chain and raises ``TruncationError`` if the store is shorter
   than the checkpoint or its hash at the checkpoint sequence differs. A store that is longer than
   the checkpoint is accepted (the checkpoint write may lag an append by one step); the caller then
   records the new checkpoint.
5. Without an independently preserved checkpoint, tail truncation is undetectable by design.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol, Sequence

from the_reef.ledger import events as ev
from the_reef.ledger.events import GENESIS_HASH, EventDraft, EventKind, LedgerEvent
from the_reef.ledger.state import ConflictError, LedgerError, LedgerState, apply, check_invariants, replay
from the_reef.market.instruments import CorporateActionSource, settlements_due


class TruncationError(LedgerError):
    """The store is shorter than, or disagrees with, the independently preserved checkpoint."""


@dataclass(frozen=True)
class Checkpoint:
    seq: int
    head_hash: str


class AppendResult(str, Enum):
    APPENDED = "APPENDED"
    DUPLICATE = "DUPLICATE"


class DiscrepancyKind(str, Enum):
    CASH_CHANGED = "CASH_CHANGED"  # the source now implies different cash for the recorded shares
    ACTION_MISSING = "ACTION_MISSING"  # the source no longer contains the recorded action (or its id changed)


@dataclass(frozen=True)
class Discrepancy:
    """A settled corporate action whose current source terms differ from what the ledger recorded.

    Reported, never applied: history is only ever changed by appending a new, explicit correcting
    event decided by a human.
    """

    event_id: str
    epoch_id: str
    sleeve_id: str
    symbol: str
    kind: DiscrepancyKind
    recorded_cash: Decimal
    current_cash: Decimal | None


class EventStore(Protocol):
    def read_all(self) -> Sequence[LedgerEvent]: ...

    def append(self, event: LedgerEvent) -> None:
        """Must raise if ``seq`` or ``event_id`` already exists. See the module docstring."""
        ...


class InMemoryEventStore:
    def __init__(self, events: Sequence[LedgerEvent] = ()) -> None:
        self._events: list[LedgerEvent] = list(events)

    def read_all(self) -> Sequence[LedgerEvent]:
        return tuple(self._events)

    def append(self, event: LedgerEvent) -> None:
        if event.seq != len(self._events) + 1:
            raise LedgerError("store sequence mismatch")
        if any(e.draft.event_id == event.draft.event_id for e in self._events):
            raise LedgerError("store already holds this event_id")
        self._events.append(event)


def verify_checkpoint(events: Sequence[LedgerEvent], expected: Checkpoint) -> None:
    if expected.seq == 0:
        return
    if len(events) < expected.seq:
        raise TruncationError(f"store holds {len(events)} events; checkpoint says at least {expected.seq}")
    if events[expected.seq - 1].hash != expected.head_hash:
        raise TruncationError(f"history at seq {expected.seq} differs from the preserved checkpoint")


class Ledger:
    def __init__(self, store: EventStore | None = None, expected: Checkpoint | None = None) -> None:
        self.store: EventStore = store or InMemoryEventStore()
        events = list(self.store.read_all())
        self._state = replay(events)  # verifies the chain on load
        if expected is not None:
            verify_checkpoint(events, expected)

    @property
    def state(self) -> LedgerState:
        return self._state

    def checkpoint(self) -> Checkpoint:
        """The head to preserve independently after each append (see the module contract)."""
        return Checkpoint(self._state.last_seq, self._state.head_hash or GENESIS_HASH)

    def append(self, draft: EventDraft) -> AppendResult:
        known = self._state.seen.get(draft.event_id)
        if known is not None:
            if known == draft.fingerprint:
                return AppendResult.DUPLICATE
            raise ConflictError(f"event_id {draft.event_id} already recorded with different content")
        event = LedgerEvent.link(self._state.last_seq + 1, self._state.head_hash or GENESIS_HASH, draft)
        new_state = apply(self._state, event)
        check_invariants(new_state)
        self.store.append(event)
        self._state = new_state
        return AppendResult.APPENDED

    def settle_corporate_actions(
        self, sleeve_ids: Sequence[str], actions: CorporateActionSource, session_day: date, at: datetime,
    ) -> list[AppendResult]:
        """Cash out every holder's names whose acquisition is effective, exactly once per epoch,
        sleeve and action.

        Safe to call every session: ids the ledger already holds are skipped. A settled action is
        never re-settled and never altered here, even if the source later changes its terms; call
        ``settlement_discrepancies`` to surface that.
        """
        epoch = self._state.epoch()
        results: list[AppendResult] = []
        for sid in sleeve_ids:
            due = settlements_due(
                epoch.holdings(sid), actions, session_day, holder=sid, as_of=at,
                already_settled=set(self._state.seen), scope=epoch.epoch_id,
            )
            for c in due:
                results.append(self.append(ev.corporate_action_settled(
                    epoch.epoch_id, at, sleeve_id=sid, symbol=c.symbol, shares=c.shares, cash=c.cash,
                    action_id=c.action_id, effective=c.effective,
                )))
        return results

    def settlement_discrepancies(self, actions: CorporateActionSource, as_of: datetime) -> list[Discrepancy]:
        """Compare every recorded settlement with the source as known at ``as_of``. Read-only."""
        found: list[Discrepancy] = []
        for e in self.store.read_all():
            d = e.draft
            if d.kind is not EventKind.CORPORATE_ACTION_SETTLED:
                continue
            p = d.payload
            recorded = Decimal(str(p["cash"]))
            current = next((a for a in actions.actions_for(str(p["symbol"]), as_of) if a.action_id == p["action_id"]), None)
            cash = None if current is None or current.cash_per_share is None else current.cash_per_share * int(p["shares"])
            if cash is None:
                kind = DiscrepancyKind.ACTION_MISSING
            elif cash != recorded:
                kind = DiscrepancyKind.CASH_CHANGED
            else:
                continue
            found.append(Discrepancy(d.event_id, d.epoch_id, str(p["sleeve_id"]), str(p["symbol"]), kind, recorded, cash))
        return found
