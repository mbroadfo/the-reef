from __future__ import annotations

import random
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tests.fixtures.market import SEM_DEAL, standard_actions
from the_reef.ledger import events as ev
from the_reef.ledger.events import LedgerEvent, Side
from the_reef.ledger.ledger import (
    AppendResult,
    Checkpoint,
    DiscrepancyKind,
    InMemoryEventStore,
    Ledger,
    TruncationError,
)
from the_reef.ledger.state import ConflictError, LedgerError, check_invariants, replay
from the_reef.ledger.views import fund_view, sleeve_cash
from the_reef.market.instruments import StaticCorporateActions, settlements_due
from the_reef.risk.engine import RejectCode, evaluate_entry
from the_reef.risk.limits import RiskLimits

D = Decimal
T0 = datetime(2026, 7, 6, 13, 30, tzinfo=timezone.utc)
E1 = "epoch-1"
DAY = date(2026, 7, 6)


def at(minutes=0):
    return T0 + timedelta(minutes=minutes)


def fresh(sleeves=("hunter", "value"), fund=("2000", "2000")) -> Ledger:
    led = Ledger()
    led.append(ev.epoch_opened(E1, at(), D("10000")))
    for sid, amt in zip(sleeves, fund):
        led.append(ev.sleeve_created(E1, at(), sid))
        led.append(ev.sleeve_funded(E1, at(), sid, D(amt), ref="alloc-0"))
    return led


def buy(led, sleeve, sym, shares, price, order, stop=None, minute=1):
    return led.append(ev.fill(E1, at(minute), sleeve_id=sleeve, order_id=order, symbol=sym, side=Side.BUY,
                              shares=shares, price=D(price), session_day=DAY,
                              stop_price=None if stop is None else D(stop)))


def sell(led, sleeve, sym, shares, price, order, minute=2):
    return led.append(ev.fill(E1, at(minute), sleeve_id=sleeve, order_id=order, symbol=sym, side=Side.SELL,
                              shares=shares, price=D(price), session_day=DAY))


# --- structure: one fund, independent sleeves -------------------------------------------------

def test_epoch_opens_all_cash_and_sleeves_are_funded_from_it():
    led = fresh()
    ep = led.state.epoch()
    assert ep.initial_cash == D(10000) and ep.unallocated == D(6000) and ep.cash == D(10000)
    assert sleeve_cash(ep, "hunter") == D(2000)


def test_sleeves_are_independent():
    led = fresh()
    buy(led, "hunter", "AAPL", 10, "100", "o1", stop="95")
    ep = led.state.epoch()
    assert ep.sleeves["hunter"].cash == D(1000) and ep.sleeves["value"].cash == D(2000)
    assert ep.sleeves["value"].positions == {}
    with pytest.raises(LedgerError):  # value cannot sell what only hunter holds
        sell(led, "value", "AAPL", 1, "100", "o2")


def test_a_sleeve_cannot_spend_more_than_it_holds_or_borrow_from_another():
    led = fresh()
    with pytest.raises(LedgerError, match="exceeds sleeve cash"):
        buy(led, "hunter", "AAPL", 21, "100", "big")
    assert led.state.epoch().sleeves["value"].cash == D(2000)


def test_funding_cannot_exceed_unallocated_cash_and_defunding_cannot_exceed_sleeve_cash():
    led = fresh()
    with pytest.raises(LedgerError):
        led.append(ev.sleeve_funded(E1, at(), "hunter", D(7000), ref="too-much"))
    with pytest.raises(LedgerError):
        led.append(ev.sleeve_funded(E1, at(), "hunter", D(-2500), ref="too-much-back"))
    led.append(ev.sleeve_funded(E1, at(), "hunter", D(-500), ref="trim"))
    assert led.state.epoch().unallocated == D(6500)


# --- fills: whole shares, no shorting, cost basis, realized P&L ----------------------------------

def test_buy_then_partial_and_full_sell_realize_pnl_from_average_cost():
    led = fresh()
    buy(led, "hunter", "AAPL", 10, "100", "o1", stop="95")
    buy(led, "hunter", "AAPL", 5, "120", "o2", stop="110")
    pos = led.state.epoch().sleeves["hunter"].positions["AAPL"]
    assert (pos.shares, pos.cost, pos.stop_price) == (15, D(1600), D(110))
    sell(led, "hunter", "AAPL", 5, "130", "o3")  # removes 1600*5/15 = 533.33333333 of cost
    sl = led.state.epoch().sleeves["hunter"]
    assert sl.positions["AAPL"].shares == 10 and sl.realized_pnl == D("116.66666667")
    sell(led, "hunter", "AAPL", 10, "90", "o4")
    sl = led.state.epoch().sleeves["hunter"]
    assert sl.positions == {} and sl.realized_pnl == D(-50)  # proceeds 1550 - cost 1600, exactly
    assert sl.cash == D(1950)
    check_invariants(led.state)


@pytest.mark.parametrize("shares", [0, -1, 1.5, True])
def test_only_positive_whole_shares(shares):
    led = fresh()
    with pytest.raises(LedgerError):
        led.append(ev.fill(E1, at(1), sleeve_id="hunter", order_id="x", symbol="AAPL", side=Side.BUY,
                           shares=shares, price=D(10), session_day=DAY))  # type: ignore[arg-type]


def test_no_shorting_and_no_oversell():
    led = fresh()
    with pytest.raises(LedgerError, match="no shorting"):
        sell(led, "hunter", "AAPL", 1, "100", "s0")
    buy(led, "hunter", "AAPL", 5, "100", "o1")
    with pytest.raises(LedgerError, match="no shorting"):
        sell(led, "hunter", "AAPL", 6, "100", "s1")


def test_stop_must_be_below_the_fill_price_and_needs_a_position():
    led = fresh()
    with pytest.raises(LedgerError, match="below the fill price"):
        buy(led, "hunter", "AAPL", 1, "100", "o1", stop="100")
    with pytest.raises(LedgerError, match="no position"):
        led.append(ev.stop_updated(E1, at(1), "hunter", "AAPL", D(90), ref="r1"))
    buy(led, "hunter", "AAPL", 1, "100", "o2", stop="90")
    led.append(ev.stop_updated(E1, at(2), "hunter", "AAPL", D(95), ref="r2"))
    assert led.state.epoch().sleeves["hunter"].positions["AAPL"].stop_price == D(95)


def test_events_cannot_go_back_in_time():
    led = fresh()
    buy(led, "hunter", "AAPL", 1, "100", "o1", minute=5)
    with pytest.raises(LedgerError, match="precedes"):
        buy(led, "hunter", "AAPL", 1, "100", "o2", minute=1)


# --- immutability and idempotency -------------------------------------------------------------

def test_a_retried_fill_is_a_no_op():
    led = fresh()
    assert buy(led, "hunter", "AAPL", 10, "100", "o1") is AppendResult.APPENDED
    before, seq = led.state.digest(), led.state.last_seq
    assert buy(led, "hunter", "AAPL", 10, "100", "o1") is AppendResult.DUPLICATE
    assert led.state.digest() == before and led.state.last_seq == seq
    assert len(led.store.read_all()) == seq


def test_the_same_order_with_different_content_is_a_conflict_not_an_overwrite():
    led = fresh()
    buy(led, "hunter", "AAPL", 10, "100", "o1")
    with pytest.raises(ConflictError):
        buy(led, "hunter", "AAPL", 11, "100", "o1")
    with pytest.raises(ConflictError):
        buy(led, "hunter", "AAPL", 10, "101", "o1")
    assert led.state.epoch().sleeves["hunter"].positions["AAPL"].shares == 10


def test_the_same_order_id_in_two_sleeves_is_two_distinct_fills():
    led = fresh()
    assert buy(led, "hunter", "AAPL", 1, "100", "o1") is AppendResult.APPENDED
    assert buy(led, "value", "AAPL", 1, "100", "o1") is AppendResult.APPENDED


def test_a_rejected_event_leaves_no_trace_and_can_be_retried_after_the_cause_is_fixed():
    led = fresh()
    d0, n0 = led.state.digest(), len(led.store.read_all())
    with pytest.raises(LedgerError):
        buy(led, "hunter", "AAPL", 70, "100", "big")
    assert led.state.digest() == d0 and len(led.store.read_all()) == n0
    led.append(ev.sleeve_funded(E1, at(1), "hunter", D(5000), ref="top-up"))
    assert buy(led, "hunter", "AAPL", 70, "100", "big", minute=2) is AppendResult.APPENDED


def test_tampering_breaks_the_chain():
    led = fresh()
    buy(led, "hunter", "AAPL", 10, "100", "o1")
    events = list(led.store.read_all())
    target = events[-1]
    forged_draft = replace(target.draft, payload={**target.draft.payload, "price": "1"})
    forged = LedgerEvent(target.seq, target.prev_hash, target.hash, forged_draft)
    with pytest.raises(LedgerError, match="hash"):
        replay(events[:-1] + [forged])
    with pytest.raises(LedgerError):
        Ledger(InMemoryEventStore(events[:-1] + [forged]))


def test_a_dropped_or_reordered_event_is_detected():
    led = fresh()
    buy(led, "hunter", "AAPL", 1, "100", "o1")
    buy(led, "hunter", "AAPL", 1, "100", "o2", minute=2)
    events = list(led.store.read_all())
    with pytest.raises(LedgerError):
        replay(events[:-2] + events[-1:])
    with pytest.raises(LedgerError):
        replay(events[:-2] + [events[-1], events[-2]])


# --- deterministic replay ---------------------------------------------------------------------

def script(led):
    buy(led, "hunter", "AAPL", 10, "100", "o1", stop="95")
    buy(led, "value", "FIZZ", 20, "50", "o2", stop="45", minute=2)
    sell(led, "hunter", "AAPL", 4, "104", "o3", minute=3)


def test_replay_reproduces_state_and_hash_exactly():
    a, b = fresh(), fresh()
    script(a)
    script(b)
    assert a.state.digest() == b.state.digest() and a.state.head_hash == b.state.head_hash
    replayed = replay(list(a.store.read_all()))
    assert replayed.digest() == a.state.digest() and replayed.head_hash == a.state.head_hash
    assert Ledger(InMemoryEventStore(a.store.read_all())).state.digest() == a.state.digest()


def test_replaying_a_prefix_gives_the_state_at_that_point():
    led = fresh()
    script(led)
    events = list(led.store.read_all())
    prefix = replay(events[:-1])
    assert prefix.epoch().sleeves["hunter"].positions["AAPL"].shares == 10
    assert led.state.epoch().sleeves["hunter"].positions["AAPL"].shares == 6


# --- epochs: one active at a time, nothing carries over ----------------------------------------

def test_one_active_epoch_and_a_closed_epoch_accepts_nothing():
    led = fresh()
    with pytest.raises(LedgerError, match="already active"):
        led.append(ev.epoch_opened("epoch-2", at(1), D("10000")))
    buy(led, "hunter", "AAPL", 1, "100", "o1")
    led.append(ev.epoch_closed(E1, at(2), "test"))
    assert led.state.active_epoch is None
    with pytest.raises(LedgerError, match="closed"):
        buy(led, "hunter", "AAPL", 1, "100", "o2", minute=3)


def test_a_new_epoch_starts_from_cash_with_no_carry_over():
    led = fresh()
    buy(led, "hunter", "AAPL", 10, "100", "o1")
    led.append(ev.epoch_closed(E1, at(2)))
    led.append(ev.epoch_opened("epoch-2", at(3), D("10000")))
    e2 = led.state.epoch()
    assert e2.epoch_id == "epoch-2" and e2.sleeves == {} and e2.unallocated == D(10000)
    assert led.state.epochs[E1].sleeves["hunter"].positions["AAPL"].shares == 10  # archive intact
    led.append(ev.sleeve_created("epoch-2", at(4), "hunter"))  # same sleeve name, separate books
    led.append(ev.sleeve_funded("epoch-2", at(4), "hunter", D(1000), ref="alloc-0"))
    assert led.state.epoch().sleeves["hunter"].positions == {}
    with pytest.raises(LedgerError):  # a sell cannot touch epoch-1's shares from epoch 2
        led.append(ev.fill("epoch-2", at(5), sleeve_id="hunter", order_id="o1", symbol="AAPL", side=Side.SELL,
                           shares=1, price=D(100), session_day=DAY))
    check_invariants(led.state)


def test_initial_cash_must_be_positive():
    with pytest.raises(LedgerError):
        Ledger().append(ev.epoch_opened(E1, at(), D(0)))


# --- corporate actions through the ledger ------------------------------------------------------

def sem_book():
    led = fresh()
    buy(led, "hunter", "SEM", 100, "15", "sem-h", stop="10")
    buy(led, "value", "SEM", 50, "15", "sem-v", stop="10", minute=2)
    return led


def test_cash_out_settles_each_sleeve_once_from_the_filed_price():
    led = sem_book()
    when = at(10)
    first = led.settle_corporate_actions(["hunter", "value"], standard_actions(), DAY, when)
    assert first == [AppendResult.APPENDED, AppendResult.APPENDED]
    ep = led.state.epoch()
    assert ep.sleeves["hunter"].positions == {} and ep.sleeves["hunter"].cash == D(500) + D(1650)
    assert ep.sleeves["value"].cash == D(1250) + D(825)
    assert ep.sleeves["hunter"].realized_pnl == D(150) and ep.sleeves["value"].realized_pnl == D(75)
    digest, n = led.state.digest(), len(led.store.read_all())
    assert led.settle_corporate_actions(["hunter", "value"], standard_actions(), DAY, when) == []
    assert led.state.digest() == digest and len(led.store.read_all()) == n
    check_invariants(led.state)


def test_settlement_survives_restated_source_rows_and_a_restart():
    led = sem_book()
    restated = replace(SEM_DEAL, known_at=datetime(2026, 6, 15, tzinfo=timezone.utc), evidence=("amended",))
    src = StaticCorporateActions([SEM_DEAL, restated, SEM_DEAL])
    led.settle_corporate_actions(["hunter", "value"], src, DAY, at(10))
    reloaded = Ledger(InMemoryEventStore(led.store.read_all()))  # restart
    assert reloaded.settle_corporate_actions(["hunter", "value"], src, DAY, at(11)) == []


def test_settlement_before_the_effective_date_does_nothing():
    led = sem_book()
    assert led.settle_corporate_actions(["hunter"], standard_actions(), date(2026, 6, 30), at(10)) == []
    assert led.state.epoch().sleeves["hunter"].positions["SEM"].shares == 100


def test_a_settlement_with_the_wrong_share_count_or_a_foreign_id_is_refused():
    led = sem_book()
    [due] = settlements_due({"SEM": 100}, standard_actions(), DAY, holder="hunter", as_of=at(10), scope=E1)
    wrong = ev.corporate_action_settled(E1, at(10), sleeve_id="hunter", symbol="SEM", shares=99, cash=D("1633.5"),
                                        action_id=due.action_id, effective=due.effective)
    with pytest.raises(LedgerError, match="does not match"):
        led.append(wrong)
    forged = replace(ev.corporate_action_settled(E1, at(10), sleeve_id="hunter", symbol="SEM", shares=100,
                                                 cash=due.cash, action_id=due.action_id, effective=due.effective),
                     event_id="made-up-id")
    with pytest.raises(LedgerError, match="derived from epoch, sleeve and action"):
        led.append(forged)
    good = ev.corporate_action_settled(E1, at(10), sleeve_id="hunter", symbol="SEM", shares=100, cash=due.cash,
                                       action_id=due.action_id, effective=due.effective)
    assert good.event_id == due.event_id
    led.append(good)
    changed = ev.corporate_action_settled(E1, at(11), sleeve_id="hunter", symbol="SEM", shares=100, cash=D(1700),
                                          action_id=due.action_id, effective=due.effective)
    with pytest.raises(ConflictError):
        led.append(changed)


def _settled(epoch, sleeve, action):
    return ev.corporate_action_settled(epoch, at(), sleeve_id=sleeve, symbol="SEM", shares=1, cash=D(1),
                                       action_id=action, effective=DAY).event_id


def test_settlement_identity_is_unique_per_epoch_sleeve_and_action():
    base = _settled("e1", "s", "act")
    assert base != _settled("e2", "s", "act")
    assert base != _settled("e1", "t", "act")
    assert base != _settled("e1", "s", "other")


def test_the_same_action_and_sleeve_settle_independently_in_two_epochs():
    led = sem_book()
    assert led.settle_corporate_actions(["hunter"], standard_actions(), DAY, at(10)) == [AppendResult.APPENDED]
    led.append(ev.epoch_closed(E1, at(11)))
    led.append(ev.epoch_opened("epoch-2", at(12), D("10000")))
    led.append(ev.sleeve_created("epoch-2", at(12), "hunter"))
    led.append(ev.sleeve_funded("epoch-2", at(12), "hunter", D(2000), ref="alloc-0"))
    led.append(ev.fill("epoch-2", at(13), sleeve_id="hunter", order_id="sem-h", symbol="SEM", side=Side.BUY,
                       shares=100, price=D(15), session_day=DAY, stop_price=D(10)))  # same order id, new epoch
    assert led.settle_corporate_actions(["hunter"], standard_actions(), DAY, at(14)) == [AppendResult.APPENDED]
    assert led.settle_corporate_actions(["hunter"], standard_actions(), DAY, at(15)) == []
    ids = [e.draft.event_id for e in led.store.read_all() if e.draft.kind.value == "CORPORATE_ACTION_SETTLED"]
    assert len(ids) == 2 and len(set(ids)) == 2
    assert led.state.epochs[E1].sleeves["hunter"].cash == D(500) + D(1650)
    assert led.state.epochs["epoch-2"].sleeves["hunter"].cash == D(500) + D(1650)
    check_invariants(led.state)


# --- settled actions are history: later source changes are reported, not applied -----------------

def test_a_restated_cash_price_after_settlement_is_a_discrepancy_not_a_rewrite():
    led = sem_book()
    led.settle_corporate_actions(["hunter", "value"], standard_actions(), DAY, at(10))
    assert led.settlement_discrepancies(standard_actions(), at(11)) == []
    before, n = led.state.digest(), len(led.store.read_all())
    restated = replace(SEM_DEAL, known_at=at(20), cash_per_share=D("17.00"))
    src = StaticCorporateActions([SEM_DEAL, restated])
    assert led.settle_corporate_actions(["hunter", "value"], src, DAY, at(21)) == []  # nothing re-settles
    found = led.settlement_discrepancies(src, at(21))
    assert {(d.sleeve_id, d.kind) for d in found} == {
        ("hunter", DiscrepancyKind.CASH_CHANGED), ("value", DiscrepancyKind.CASH_CHANGED)}
    h = next(d for d in found if d.sleeve_id == "hunter")
    assert (h.recorded_cash, h.current_cash, h.epoch_id, h.symbol) == (D(1650), D(1700), E1, "SEM")
    assert led.state.digest() == before and len(led.store.read_all()) == n  # history untouched
    assert led.settlement_discrepancies(src, at(15)) == []  # before the restatement was known


def test_a_withdrawn_or_re_identified_action_is_a_discrepancy():
    led = sem_book()
    led.settle_corporate_actions(["hunter"], standard_actions(), DAY, at(10))
    gone = led.settlement_discrepancies(StaticCorporateActions([]), at(11))
    assert [d.kind for d in gone] == [DiscrepancyKind.ACTION_MISSING]
    moved = StaticCorporateActions([replace(SEM_DEAL, effective=date(2026, 7, 2))])  # new effective = new id
    assert [d.kind for d in led.settlement_discrepancies(moved, at(11))] == [DiscrepancyKind.ACTION_MISSING]


# --- immutability of retained references ---------------------------------------------------------

def test_mutating_the_dict_a_draft_was_built_from_cannot_change_the_event():
    payload = {"sleeve_id": "x", "nested": {"a": [1, 2]}}
    draft = ev.EventDraft("id-1", E1, ev.EventKind.SLEEVE_CREATED, at(), payload)
    fingerprint = draft.fingerprint
    payload["sleeve_id"] = "tampered"
    payload["nested"]["a"].append(3)
    assert draft.payload["sleeve_id"] == "x" and draft.payload["nested"]["a"] == (1, 2)
    assert draft.fingerprint == fingerprint


def test_a_payload_cannot_be_mutated_through_the_event():
    draft = ev.EventDraft("id-1", E1, ev.EventKind.SLEEVE_CREATED, at(), {"sleeve_id": "x", "n": {"a": 1}})
    with pytest.raises(TypeError):
        draft.payload["sleeve_id"] = "y"  # type: ignore[index]
    with pytest.raises(TypeError):
        draft.payload["n"]["a"] = 2  # type: ignore[index]
    with pytest.raises(TypeError):
        del draft.payload["sleeve_id"]  # type: ignore[attr-defined]


def test_appended_events_survive_attempts_to_alter_them_through_retained_references():
    led = fresh()
    d = ev.fill(E1, at(1), sleeve_id="hunter", order_id="o1", symbol="AAPL", side=Side.BUY, shares=10,
                price=D(100), session_day=DAY)
    led.append(d)
    digest, head = led.state.digest(), led.state.head_hash
    stored = led.store.read_all()[-1]
    for victim in (d, stored.draft):
        with pytest.raises(TypeError):
            victim.payload["shares"] = 1000  # type: ignore[index]
    with pytest.raises(AttributeError):
        stored.draft.event_id = "x"  # type: ignore[misc]
    with pytest.raises(TypeError):
        led.state.epoch().sleeves["hunter"].positions["AAPL"] = None  # type: ignore[index]
    with pytest.raises(TypeError):
        led.state.epoch().sleeves["rogue"] = None  # type: ignore[index]
    with pytest.raises(TypeError):
        led.state.epochs[E1] = None  # type: ignore[index]
    with pytest.raises(TypeError):
        led.state.seen[d.event_id] = "forged"  # type: ignore[index]
    assert Ledger(InMemoryEventStore(led.store.read_all())).state.digest() == digest == led.state.digest()
    assert led.state.head_hash == head and all(e.verify() for e in led.store.read_all())


# --- hash chain: what it can and cannot prove -----------------------------------------------------

def test_tail_truncation_is_a_valid_chain_and_only_a_preserved_checkpoint_catches_it():
    led = fresh()
    buy(led, "hunter", "AAPL", 10, "100", "o1")
    cp = led.checkpoint()
    buy(led, "hunter", "AAPL", 5, "100", "o2", minute=2)
    events = list(led.store.read_all())
    truncated = events[:-1]
    assert replay(truncated).last_seq == len(events) - 1  # the chain alone cannot tell
    assert Ledger(InMemoryEventStore(truncated)).state.last_seq == len(events) - 1
    full_cp = led.checkpoint()
    with pytest.raises(TruncationError):
        Ledger(InMemoryEventStore(truncated), expected=full_cp)
    Ledger(InMemoryEventStore(truncated), expected=cp)  # the older checkpoint is still satisfied
    assert cp.seq < full_cp.seq


def test_a_store_longer_than_the_checkpoint_is_accepted():
    led = fresh()
    cp = led.checkpoint()
    buy(led, "hunter", "AAPL", 10, "100", "o1")
    assert Ledger(InMemoryEventStore(led.store.read_all()), expected=cp).state.last_seq == cp.seq + 1


def test_a_consistently_rechained_rewrite_is_caught_by_the_checkpoint():
    led = fresh()
    buy(led, "hunter", "AAPL", 10, "100", "o1")
    buy(led, "hunter", "AAPL", 5, "100", "o2", minute=2)
    cp = led.checkpoint()
    rewritten, prev = [], ev.GENESIS_HASH
    for e in led.store.read_all():
        draft = e.draft
        if draft.event_id == ev.fill_id(E1, "hunter", "o1"):
            draft = replace(draft, payload={**draft.payload, "price": "99"})
        link = LedgerEvent.link(e.seq, prev, draft)
        rewritten.append(link)
        prev = link.hash
    assert Ledger(InMemoryEventStore(rewritten)).state.last_seq == cp.seq  # chain-valid
    with pytest.raises(TruncationError, match="differs"):
        Ledger(InMemoryEventStore(rewritten), expected=cp)


def test_an_empty_store_fails_any_nonzero_checkpoint_and_the_genesis_checkpoint_is_trivial():
    led = fresh()
    with pytest.raises(TruncationError):
        Ledger(InMemoryEventStore(), expected=led.checkpoint())
    Ledger(InMemoryEventStore(), expected=Ledger().checkpoint())
    assert Ledger().checkpoint() == Checkpoint(0, ev.GENESIS_HASH)


def test_checkpoints_advance_with_every_append_and_not_with_duplicates():
    led = fresh()
    before = led.checkpoint()
    buy(led, "hunter", "AAPL", 1, "100", "o1")
    after = led.checkpoint()
    assert after.seq == before.seq + 1 and after.head_hash != before.head_hash
    buy(led, "hunter", "AAPL", 1, "100", "o1")  # duplicate
    assert led.checkpoint() == after


# --- hand-off to the Risk Engine ----------------------------------------------------------------

def test_fund_view_aggregates_sleeves_and_carries_stops():
    led = fresh()
    buy(led, "hunter", "AAPL", 10, "100", "o1", stop="95")
    buy(led, "value", "AAPL", 5, "100", "o2", stop="98", minute=2)
    view = fund_view(led.state.epoch(), {"AAPL": D(100)}, {"AAPL": "Technology"},
                     prior_close_nav=D(10000), high_water_mark=D(10000))
    assert view.nav == D(10000) and view.book_trusted and view.shares_of("AAPL") == 15
    assert view.stop_risk_of("AAPL") == D(50) + D(10)


def test_unmarkable_position_makes_the_book_untrusted_and_blocks_entries_not_exits():
    led = fresh()
    buy(led, "hunter", "AAPL", 10, "100", "o1", stop="95")
    view = fund_view(led.state.epoch(), {"AAPL": None}, {"AAPL": "Technology"},
                     prior_close_nav=D(10000), high_water_mark=D(10000))
    assert not view.book_trusted
    d = evaluate_entry(symbol="FIZZ", sector="Consumer", ref_price=D(50), stop_price=D(48),
                       sleeve_cash=sleeve_cash(led.state.epoch(), "value"), portfolio=view, limits=RiskLimits())
    assert not d.approved and RejectCode.BOOK_UNTRUSTED in d.reasons


def test_risk_engine_sees_the_stop_risk_the_ledger_holds():
    led = fresh()
    buy(led, "hunter", "AAPL", 50, "10", "o1", stop="9")  # 50 x 1 = the whole 0.5% risk budget
    view = fund_view(led.state.epoch(), {"AAPL": D(10)}, {"AAPL": "Technology"},
                     prior_close_nav=D(10000), high_water_mark=D(10000))
    d = evaluate_entry(symbol="AAPL", sector="Technology", ref_price=D(10), stop_price=D(9),
                       sleeve_cash=sleeve_cash(led.state.epoch(), "value"), portfolio=view, limits=RiskLimits())
    assert not d.approved and d.reasons == (RejectCode.RISK_BUDGET_EXHAUSTED,)


# --- invariants under a long random run ----------------------------------------------------------

def test_random_operations_keep_the_books_balanced_and_replay_identically():
    rnd = random.Random(20261031)
    led = fresh(sleeves=("a", "b", "c"), fund=("2000", "2000", "2000"))
    symbols = ["AAPL", "FIZZ", "MSFT", "SEM"]
    applied = rejected = 0
    for step in range(2500):
        sid = rnd.choice(["a", "b", "c"])
        sym = rnd.choice(symbols)
        before = led.state.digest()
        roll = rnd.random()
        price = D(rnd.randint(5, 300))
        if roll < 0.45:
            d = ev.fill(E1, at(1 + step), sleeve_id=sid, order_id=f"o{step}", symbol=sym, side=Side.BUY,
                        shares=rnd.randint(1, 15), price=price, session_day=DAY,
                        stop_price=price - D(rnd.randint(1, 4)))
        elif roll < 0.8:
            d = ev.fill(E1, at(1 + step), sleeve_id=sid, order_id=f"o{step}", symbol=sym, side=Side.SELL,
                        shares=rnd.randint(1, 15), price=price, session_day=DAY)
        elif roll < 0.9:
            d = ev.sleeve_funded(E1, at(1 + step), sid, D(rnd.randint(-500, 500)) or D(1), ref=f"f{step}")
        else:
            d = ev.stop_updated(E1, at(1 + step), sid, sym, price, ref=f"s{step}")
        try:
            led.append(d)
            applied += 1
        except LedgerError:
            rejected += 1
            assert led.state.digest() == before  # a rejected event changes nothing
        check_invariants(led.state)
    assert applied > 500 and rejected > 100  # exercised both paths
    replayed = replay(list(led.store.read_all()))
    assert replayed.digest() == led.state.digest()
