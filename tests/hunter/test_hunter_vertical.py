"""The Hunter vertical slice end to end, on the synthetic scenario in tests/fixtures/hunter_scenario.py."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from tests.fixtures.hunter_scenario import EPOCH_ID, SLEEVE, START_INDEX, UNIVERSE, make_deps
from tests.hunter.conftest import run, start
from the_reef.engine.advance import NoteKind
from the_reef.ledger.events import EventKind
from the_reef.ledger.ledger import InMemoryEventStore, Ledger
from the_reef.ledger.state import OrderStatus, check_invariants, replay
from the_reef.performance.metrics import (
    buy_and_hold,
    fund_nav_series,
    funded_capital,
    max_drawdown,
    round_trips,
    sleeve_nav_series,
    total_return,
)

D = Decimal


def notes(reports, kind, symbol=None):
    return [(r.session_day, n) for r in reports for n in r.notes if n.kind is kind and (symbol is None or n.symbol == symbol)]


def fills(led, symbol):
    return [e.draft.payload for e in led.store.read_all()
            if e.draft.kind is EventKind.FILL and e.draft.payload["symbol"] == symbol]


# --- discovery, proposal, entry -----------------------------------------------------------------

def test_hunter_discovers_hunt_proposes_it_and_enters_at_the_next_open(full_run):
    deps, led, reports = full_run
    queued = [(d, n) for d, n in notes(reports, NoteKind.QUEUED, "HUNT") if n.detail.startswith("open")]
    assert queued, "HUNT was never proposed"
    decided_day, note = queued[0]
    assert decided_day == date(2026, 8, 28) and "breakout: close 102.59 > 20d high 101.84" in note.detail
    assert "stop 99.50" in note.detail
    entry = fills(led, "HUNT")[0]
    assert entry["side"] == "BUY" and entry["session_day"] == "2026-08-31"  # next session, not the decision day
    assert (entry["shares"], entry["price"]) == (9, "102.40")  # the official open, not the 102.59 close
    order = led.state.epoch().orders[f"{SLEEVE}:hunter-momentum:2026-08-28:HUNT:open"]
    assert order.status is OrderStatus.FILLED and order.stop_price == D("99.50") and order.requested_shares == 10


def test_the_entry_was_sized_by_the_risk_engine_at_the_open_price_not_the_close(full_run):
    deps, led, reports = full_run
    _, note = notes(reports, NoteKind.FILL, "HUNT")[0]
    # D0 allowed up to 10 shares; floor(10% of $10,000 / 102.40) = 9, so Risk sized it down at the open price.
    assert "BUY 9 @ 102.40" in note.detail


# --- risk refusals and data failures ------------------------------------------------------------

def test_bigp_passes_the_signal_but_fails_risk(full_run):
    deps, led, reports = full_run
    refusals = [n.detail for _, n in notes(reports, NoteKind.DECISION_REJECTED, "BIGP")]
    assert any(d.startswith("RISK_REJECTED:SIZE_ZERO") for d in refusals)  # 10% cap < one $1,500 share
    assert fills(led, "BIGP") == []


def test_deal_is_refused_by_the_tradability_gate_while_a_cash_acquisition_is_pending(full_run):
    deps, led, reports = full_run
    refusals = [n.detail for _, n in notes(reports, NoteKind.DECISION_REJECTED, "DEAL")]
    assert refusals and all("PENDING_CASH_DEAL" in d for d in refusals)
    assert fills(led, "DEAL") == []


def test_a_missing_open_print_rejects_the_fill_and_nothing_is_bought_at_a_stale_price(full_run):
    deps, led, reports = full_run
    [(day, note)] = notes(reports, NoteKind.FILL_REJECTED, "GAPR")
    assert day == date(2026, 8, 21) and "NO_VALID_OPEN_PRINT" in note.detail
    order = led.state.epoch().orders[f"{SLEEVE}:hunter-momentum:2026-08-20:GAPR:open"]
    assert order.status is OrderStatus.REJECTED
    assert all(f["session_day"] != "2026-08-21" for f in fills(led, "GAPR"))


# --- valuation and exits ------------------------------------------------------------------------

def test_stops_only_ratchet_up(full_run):
    deps, led, reports = full_run
    raised = [n.detail for _, n in notes(reports, NoteKind.STOP_RAISED, "HUNT")]
    levels = [Decimal(d.split("->")[1]) for d in raised]
    assert levels == sorted(levels) and len(levels) > 5


def test_hunt_gaps_down_through_its_stop_and_fills_at_the_open_not_the_stop(full_run):
    deps, led, reports = full_run
    [(day, note)] = notes(reports, NoteKind.STOP_GAP, "HUNT")
    assert day == date(2026, 10, 16)
    exit_fill = fills(led, "HUNT")[-1]
    assert exit_fill["side"] == "SELL" and exit_fill["order_id"].startswith("stop:")
    stop_level, open_price = Decimal("131.80"), Decimal(exit_fill["price"])
    assert open_price == D("119.38") < stop_level  # worse than the stop: the gap is paid, not wished away
    [trip] = [t for t in round_trips(led.store.read_all(), EPOCH_ID, SLEEVE) if t.symbol == "HUNT"]
    assert trip.pnl == (D("119.38") - D("102.40")) * 9 and trip.exit_reason == "stop"


def test_trend_break_exits_at_the_next_open(full_run):
    deps, led, reports = full_run
    [(day, _)] = [(d, n) for d, n in notes(reports, NoteKind.QUEUED, "TRND") if n.detail.startswith("close")]
    assert day == date(2026, 10, 20)
    [trip] = [t for t in round_trips(led.store.read_all(), EPOCH_ID, SLEEVE) if t.symbol == "TRND"]
    assert trip.exit_day == "2026-10-21" and trip.exit_reason == "strategy exit"
    assert trip.pnl == (D("53.09") - D("50.40")) * 20


# --- books, accounting, performance -------------------------------------------------------------

def test_the_books_balance_and_every_session_was_marked_and_verified(full_run):
    deps, led, reports = full_run
    check_invariants(led.state)
    ep = led.state.epoch()
    assert len(ep.marks) == 65
    realized = sum((s.realized_pnl for s in ep.sleeves.values()), D("0"))
    open_cost = sum((p.cost for s in ep.sleeves.values() for p in s.positions.values()), D("0"))
    assert ep.cash + open_cost == ep.initial_cash + realized


def test_sleeve_and_fund_performance_use_their_own_capital_base(full_run):
    deps, led, reports = full_run
    events = led.store.read_all()
    funded = funded_capital(events, EPOCH_ID, SLEEVE)
    assert funded == D("4000.00")  # D0: 40% of $10,000
    sleeve = sleeve_nav_series(events, EPOCH_ID, SLEEVE)
    fund = fund_nav_series(events, EPOCH_ID)
    assert total_return(sleeve, funded) == sleeve[-1][1] / funded - 1
    # The fund's profit is exactly the sleeve's profit: the other 60% never left cash.
    assert fund[-1][1] - D(10000) == sleeve[-1][1] - funded
    assert max_drawdown(sleeve, funded) <= 0


def test_round_trips_reconcile_to_realized_pnl(full_run):
    deps, led, reports = full_run
    trips = round_trips(led.store.read_all(), EPOCH_ID, SLEEVE)
    closed_pnl = sum((t.pnl for t in trips), D("0"))
    assert closed_pnl == led.state.epoch().sleeves[SLEEVE].realized_pnl
    assert len(trips) >= 8


def test_buy_and_hold_benchmark_is_deterministic_and_whole_share(full_run, world):
    deps, led, reports = full_run
    start_day, end_day = world.days[START_INDEX], world.days[START_INDEX + 64]
    bench = buy_and_hold(world.bars, world.calendar, UNIVERSE, D("4000"), start_day, end_day)
    assert len(bench.series) == 65 and bench.cash >= 0 and sum(bench.shares.values()) > 0
    assert all(isinstance(n, int) for n in bench.shares.values())
    again = buy_and_hold(world.bars, world.calendar, UNIVERSE, D("4000"), start_day, end_day)
    assert again.series == bench.series


# --- deterministic replay -----------------------------------------------------------------------

def test_replay_reproduces_the_whole_run(full_run):
    deps, led, reports = full_run
    events = led.store.read_all()
    again = replay(list(events))
    assert again.digest() == led.state.digest() and again.head_hash == led.state.head_hash
    assert Ledger(InMemoryEventStore(events), expected=led.checkpoint()).state.digest() == led.state.digest()
    assert all(e.verify() for e in events)


def test_an_independent_run_produces_a_byte_identical_ledger(full_run, world):
    deps, led, _ = full_run
    deps2 = make_deps(world)
    led2 = start(world, deps2)
    run(world, deps2, led2, START_INDEX, START_INDEX + 64)
    assert led2.state.head_hash == led.state.head_hash and led2.state.digest() == led.state.digest()
