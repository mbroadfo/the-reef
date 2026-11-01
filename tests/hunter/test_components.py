"""Unit tests for the Hunter rules, the D0 allocator and the ledger's order and valuation events."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tests.fixtures.hunter_scenario import START_INDEX, make_deps
from tests.hunter.conftest import run, start
from the_reef.allocation.d0 import D0Config, allocate, sleeve_targets
from the_reef.engine.advance import EngineError, advance
from the_reef.ledger import events as ev
from the_reef.ledger.events import Side
from the_reef.ledger.ledger import Ledger
from the_reef.ledger.state import LedgerError, OrderStatus
from the_reef.market.bars import DailyBar
from the_reef.market.instruments import Intent
from the_reef.strategy.base import HoldingView, Proposal, StrategyContext
from the_reef.strategy.hunter import Hunter, HunterParams, atr, floor_cent

D = Decimal
UTC = timezone.utc
T0 = datetime(2026, 9, 1, 14, 0, tzinfo=UTC)


def bars(closes, volume=200_000, spread="0.50", symbol="X", start_day=date(2026, 6, 1)):
    out = []
    prev = D(str(closes[0]))
    for i, c in enumerate(closes):
        c = D(str(c))
        o = prev
        hi, lo = max(o, c) + D(spread), min(o, c) - D(spread)
        out.append(DailyBar(symbol, start_day + timedelta(days=i), o, hi, lo, c, volume, "t"))
        prev = c
    return out


def ctx(series, holdings=None, blocked=frozenset()):
    return StrategyContext(date(2026, 9, 1), T0, {"X": series}, holdings or {}, blocked)


FLAT_THEN_BREAK = [100.0] * 60 + [100.2] * 5 + [103.0]  # 66 bars, last one breaks out


# --- Hunter entry rules -------------------------------------------------------------------------

def test_breakout_above_20d_high_and_sma50_with_liquidity_is_proposed():
    [p] = Hunter().propose(ctx(bars(FLAT_THEN_BREAK)))
    assert p.symbol == "X" and p.intent is Intent.OPEN and p.ref_price == D("103.0")
    assert p.stop_price is not None and p.stop_price < p.ref_price
    a = atr(bars(FLAT_THEN_BREAK), 14)
    assert p.stop_price == floor_cent(D("103.0") - 2 * a)
    assert "breakout" in p.rationale


@pytest.mark.parametrize("series, why", [
    ([100.0] * 66, "no breakout"),
    ([100.0] * 60 + [101.0] * 5 + [100.5], "below the prior 20-day high"),
    ([150.0] * 30 + [100.0] * 31 + [100.2] * 5 + [103.0], "below the 50-day average"),
    ([100.0] * 40 + [100.2] * 5, "fewer than 51 bars"),
])
def test_no_signal_without_every_condition(series, why):
    assert Hunter().propose(ctx(bars(series))) == [], why


def test_illiquid_names_are_skipped():
    assert Hunter().propose(ctx(bars(FLAT_THEN_BREAK, volume=100))) == []


def test_held_and_blocked_names_are_not_proposed_again():
    series = bars(FLAT_THEN_BREAK)
    held = {"X": HoldingView(5, D("100"), D("98"))}
    assert Hunter().propose(ctx(series, holdings=held)) == []
    assert Hunter().propose(ctx(series, blocked=frozenset({"X"}))) == []


def test_candidates_are_ranked_by_roc_and_limited():
    strong = bars([100.0] * 60 + [100.2] * 5 + [106.0], symbol="A")
    weak = bars([100.0] * 60 + [100.2] * 5 + [101.5], symbol="B")
    mid = bars([100.0] * 60 + [100.2] * 5 + [103.0], symbol="C")
    c = StrategyContext(date(2026, 9, 1), T0, {"B": weak, "C": mid, "A": strong}, {})
    props = Hunter(HunterParams(max_candidates=2)).propose(c)
    assert [p.symbol for p in props] == ["A", "C"]


def test_the_strategy_is_deterministic_and_has_a_stable_spec_hash():
    s = bars(FLAT_THEN_BREAK)
    assert Hunter().propose(ctx(s)) == Hunter().propose(ctx(s))
    assert Hunter().spec_hash == Hunter().spec_hash
    assert Hunter().spec_hash != Hunter(HunterParams(stop_atr_mult=D("3"))).spec_hash


# --- Hunter exits and stops ---------------------------------------------------------------------

def test_trend_break_proposes_a_close():
    series = bars([100.0] * 40 + [110.0] * 20 + [104.0])
    r = Hunter().review(ctx(series, holdings={"X": HoldingView(10, D("100"), D("90"))}))
    assert [p.intent for p in r.exits] == [Intent.CLOSE] and r.new_stops == {}


def test_trailing_stop_is_raised_but_never_lowered_and_never_above_the_close():
    series = bars([100.0] * 40 + [100.0 + i * 0.5 for i in range(1, 30)])
    close = series[-1].close
    low_stop = {"X": HoldingView(10, D("100"), D("90"))}
    r = Hunter().review(ctx(series, holdings=low_stop))
    assert r.exits == () and D("90") < r.new_stops["X"] < close
    high_stop = {"X": HoldingView(10, D("100"), close - D("0.10"))}
    assert Hunter().review(ctx(series, holdings=high_stop)).new_stops == {}  # would lower it: ignored


# --- D0 -----------------------------------------------------------------------------------------

def prop(symbol, score, price):
    return Proposal(symbol, Intent.OPEN, D(str(score)), D(str(price)), D(str(price)) - 1, "t")


def test_d0_splits_sleeve_cash_equally_among_the_top_proposals():
    cfg = D0Config({"hunter": D("0.4")}, max_new_per_session=2)
    out = allocate([prop("A", 0.02, 100), prop("B", 0.05, 50), prop("C", 0.01, 10)], D("4000"), cfg)
    assert [(a.proposal.symbol, a.ceiling_shares) for a in out] == [("B", 40), ("A", 20)]  # C ranked third


def test_d0_is_deterministic_and_breaks_ties_by_symbol():
    cfg = D0Config({"hunter": D("0.4")}, max_new_per_session=1)
    a = allocate([prop("B", 0.02, 10), prop("A", 0.02, 10)], D("1000"), cfg)
    assert a[0].proposal.symbol == "A"
    assert allocate([], D("1000"), cfg) == [] and allocate([prop("A", 1, 10)], D("0"), cfg) == []


def test_d0_sleeve_targets_and_validation():
    cfg = D0Config({"hunter": D("0.4"), "value": D("0.3")})
    assert sleeve_targets(D("10000"), cfg) == {"hunter": D("4000.00"), "value": D("3000.00")}
    with pytest.raises(ValueError):
        D0Config({"a": D("0.7"), "b": D("0.4")})
    with pytest.raises(ValueError):
        D0Config({"a": D("0")})


# --- ledger: orders, valuation, session lifecycle -----------------------------------------------

def ledger_with_sleeve():
    led = Ledger()
    led.append(ev.epoch_opened("e", T0, D("10000")))
    led.append(ev.sleeve_created("e", T0, "s"))
    led.append(ev.sleeve_funded("e", T0, "s", D("4000"), ref="a"))
    return led


def queue(led, order_id="o1", shares=10, symbol="AAA", intent="open", stop="90", at=T0):
    return led.append(ev.order_queued("e", at, sleeve_id="s", order_id=order_id, symbol=symbol, intent=intent,
                                      requested_shares=shares, stop_price=None if stop is None else D(stop),
                                      fill_session=date(2026, 9, 2), ref_price=D("100"), sector="Tech"))


def fill(led, order_id="o1", shares=10, price="100", symbol="AAA", stop="90", side=Side.BUY, at=T0):
    return led.append(ev.fill("e", at, sleeve_id="s", order_id=order_id, symbol=symbol, side=side, shares=shares,
                              price=D(price), session_day=date(2026, 9, 2),
                              stop_price=None if stop is None else D(stop)))


def test_a_queued_order_is_pending_then_filled_exactly_once():
    led = ledger_with_sleeve()
    queue(led)
    assert [o.order_id for o in led.state.epoch().pending_orders()] == ["o1"]
    fill(led)
    assert led.state.epoch().orders["s:o1"].status is OrderStatus.FILLED and led.state.epoch().pending_orders() == []
    with pytest.raises(LedgerError):
        fill(led, shares=5, at=T0 + timedelta(minutes=1)).__class__  # a second, different fill of the same id


def test_a_fill_cannot_exceed_the_queued_size_or_change_symbol():
    led = ledger_with_sleeve()
    queue(led, shares=10)
    with pytest.raises(LedgerError, match="does not match"):
        fill(led, shares=11)
    with pytest.raises(LedgerError, match="does not match"):
        fill(led, symbol="BBB")
    assert led.state.epoch().orders["s:o1"].status is OrderStatus.QUEUED


def test_rejections_at_fill_need_a_pending_order_and_at_decision_must_be_new():
    led = ledger_with_sleeve()
    with pytest.raises(LedgerError, match="not pending"):
        led.append(ev.order_rejected("e", T0, sleeve_id="s", order_id="ghost", stage="FILL", code="X"))
    led.append(ev.order_rejected("e", T0, sleeve_id="s", order_id="d1", stage="DECISION", code="SIZE_ZERO"))
    assert led.state.epoch().orders["s:d1"].status is OrderStatus.REJECTED
    queue(led)
    led.append(ev.order_rejected("e", T0, sleeve_id="s", order_id="o1", stage="FILL", code="NO_VALID_OPEN_PRINT"))
    assert led.state.epoch().orders["s:o1"].status is OrderStatus.REJECTED
    with pytest.raises(LedgerError, match="rejected|REJECTED"):
        fill(led)


def test_queue_validation():
    led = ledger_with_sleeve()
    with pytest.raises(LedgerError):
        queue(led, intent="sideways")
    with pytest.raises(LedgerError):
        queue(led, shares=0)


def test_session_mark_must_match_the_books_and_cover_every_holding():
    led = ledger_with_sleeve()
    queue(led)
    fill(led)
    ok = dict(session_day=date(2026, 9, 2), marks={"AAA": D("105")}, unmarked=[], nav=D("10050"), sleeve_nav={"s": D("4050")})
    with pytest.raises(LedgerError, match="does not match"):
        led.append(ev.session_marked("e", T0, **{**ok, "nav": D("10051")}))
    with pytest.raises(LedgerError, match="neither marked nor declared"):
        led.append(ev.session_marked("e", T0, **{**ok, "marks": {}, "nav": D("10000"), "sleeve_nav": {"s": D("4000")}}))
    led.append(ev.session_marked("e", T0, **ok))
    assert led.state.epoch().marks["2026-09-02"] == D("10050")
    with pytest.raises(LedgerError, match="not after"):
        led.append(ev.session_marked("e", T0, **{**ok, "session_day": date(2026, 9, 1)}))


def test_an_unmarked_holding_is_carried_at_cost_and_declared():
    led = ledger_with_sleeve()
    queue(led)
    fill(led)
    led.append(ev.session_marked("e", T0, session_day=date(2026, 9, 2), marks={}, unmarked=["AAA"], nav=D("10000"),
                                 sleeve_nav={"s": D("4000")}))
    assert led.state.epoch().marks["2026-09-02"] == D("10000")


def test_a_session_closes_only_after_its_mark_and_only_once():
    led = ledger_with_sleeve()
    with pytest.raises(LedgerError, match="cannot close before it is marked"):
        led.append(ev.session_closed("e", T0, date(2026, 9, 2)))
    led.append(ev.session_marked("e", T0, session_day=date(2026, 9, 2), marks={}, unmarked=[], nav=D("10000"),
                                 sleeve_nav={"s": D("4000")}))
    led.append(ev.session_closed("e", T0, date(2026, 9, 2)))
    assert led.state.epoch().last_completed == "2026-09-02"
    with pytest.raises(LedgerError, match="not closed"):
        ledger2 = ledger_with_sleeve()
        ledger2.append(ev.session_marked("e", T0, session_day=date(2026, 9, 2), marks={}, unmarked=[], nav=D("10000"),
                                         sleeve_nav={"s": D("4000")}))
        ledger2.append(ev.session_marked("e", T0, session_day=date(2026, 9, 3), marks={}, unmarked=[], nav=D("10000"),
                                         sleeve_nav={"s": D("4000")}))


def test_the_engine_will_not_start_a_session_while_the_previous_one_is_unfinished(world):
    deps = make_deps(world)
    led = start(world, deps)
    run(world, deps, led, START_INDEX, START_INDEX)
    # Simulate a crash after the mark but before the session closed: drop the closing event.
    events = list(led.store.read_all())
    assert events[-1].draft.kind.value == "SESSION_CLOSED"
    from the_reef.ledger.ledger import InMemoryEventStore
    half = Ledger(InMemoryEventStore(events[:-1]))
    with pytest.raises(EngineError, match="not complete"):
        advance(half, deps, world.days[START_INDEX + 1])
    advance(half, deps, world.days[START_INDEX])  # finishing it is allowed...
    advance(half, deps, world.days[START_INDEX + 1])  # ...and then the next session can start
    assert half.state.epoch().last_completed == world.days[START_INDEX + 1].isoformat()
