"""The ledger: an append-only event store plus the state it implies.

``EventStore`` is the persistence port. Slice 2 ships only the in-memory implementation; a
database adapter must give the same guarantees (unique ``event_id`` and ``seq``, append-only,
read in ``seq`` order). Nothing here writes to a database.

``Ledger.append`` is the single write path:
  * duplicate ``event_id`` with the same content  -> ``AppendResult.DUPLICATE``, nothing written
  * duplicate ``event_id`` with different content -> ``ConflictError``
  * an event that would break an invariant        -> ``LedgerError``, nothing written
  * otherwise it is chained, applied, stored      -> ``AppendResult.APPENDED``
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Protocol, Sequence

from the_reef.ledger import events as ev
from the_reef.ledger.events import GENESIS_HASH, EventDraft, LedgerEvent
from the_reef.ledger.state import ConflictError, LedgerError, LedgerState, apply, check_invariants, replay
from the_reef.market.instruments import CorporateActionSource, settlements_due


class AppendResult(str, Enum):
    APPENDED = "APPENDED"
    DUPLICATE = "DUPLICATE"


class EventStore(Protocol):
    def read_all(self) -> Sequence[LedgerEvent]: ...

    def append(self, event: LedgerEvent) -> None:
        """Must raise if ``seq`` or ``event_id`` already exists."""
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


class Ledger:
    def __init__(self, store: EventStore | None = None) -> None:
        self.store: EventStore = store or InMemoryEventStore()
        self._state = replay(list(self.store.read_all()))  # verifies the chain on load

    @property
    def state(self) -> LedgerState:
        return self._state

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
        """Cash out every holder's names whose acquisition is effective, exactly once.

        Safe to call every session: ids the ledger already holds are skipped by
        ``settlements_due`` and, as a second line, deduplicated by ``append``.
        """
        epoch = self._state.epoch()
        results: list[AppendResult] = []
        for sid in sleeve_ids:
            due = settlements_due(
                epoch.holdings(sid), actions, session_day, holder=sid, as_of=at,
                already_settled=set(self._state.seen),
            )
            for c in due:
                results.append(self.append(ev.corporate_action_settled(
                    epoch.epoch_id, at, sleeve_id=sid, symbol=c.symbol, shares=c.shares, cash=c.cash,
                    action_id=c.action_id, effective=c.effective, event_id=c.event_id,
                )))
        return results
