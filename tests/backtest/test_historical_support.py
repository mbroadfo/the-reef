"""Cost model, cache reader and point-in-time bar source for historical replay (no vendor data)."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from tests.fixtures.hunter_scenario import START_INDEX, make_deps, make_world
from tests.hunter.conftest import run, start
from the_reef.backtest import cache
from the_reef.backtest.history import HistoricalBarSource
from the_reef.execution.costs import ExecutionCosts
from the_reef.ledger.events import EventKind
from the_reef.ledger.ledger import Ledger

D = Decimal
WORLD = make_world()
DAYS = WORLD.days


def row(day, o="100", h="101", lo="99", c="100"):
    return cache.RawRow(day, D(o), D(h), D(lo), D(c), D(c), 1000, D("0"), D("0"))


# --- costs -----------------------------------------------------------------------------------------

def test_default_costs_change_nothing():
    c = ExecutionCosts()
    assert c.buy_price(D("123.4567")) == D("123.4567") and c.sell_price(D("123.4567"), gap=True) == D("123.4567")


def test_buys_pay_up_and_sells_receive_less_rounded_against_the_trader():
    c = ExecutionCosts(slippage_bps=D("10"), gap_slippage_bps=D("50"), fee_per_share=D("0.01"))
    assert c.buy_price(D("100")) == D("100.11")        # 100.10 + 0.01
    assert c.sell_price(D("100")) == D("99.89")        # 99.90 - 0.01
    assert c.sell_price(D("100"), gap=True) == D("99.39")  # 60 bps total
    assert c.buy_price(D("10.001")) == D("10.03")      # 10.021 rounds up
    assert c.sell_price(D("0.001")) == D("0.01")       # never non-positive


def test_costs_lower_the_result_and_every_fill_is_on_the_losing_side_of_the_open():
    world = make_world()

    def go(costs):
        deps = replace(make_deps(world), costs=costs)
        led = start(world, deps)
        run(world, deps, led, START_INDEX, START_INDEX + 64)
        return deps, led

    d0, free = go(ExecutionCosts())
    d1, paid = go(ExecutionCosts(D("10"), D("50"), D("0.01")))
    nav0 = free.state.epoch().marks[max(free.state.epoch().marks)]
    nav1 = paid.state.epoch().marks[max(paid.state.epoch().marks)]
    assert nav1 < nav0
    for e in paid.store.read_all():
        p = e.draft.payload
        if e.draft.kind is EventKind.FILL and not str(p["order_id"]).startswith("stop:"):
            sess = d1.calendar.session(date.fromisoformat(p["session_day"]))
            ref = world.bars.official_open(p["symbol"], sess).price
            px = D(str(p["price"]))
            assert (px > ref) if p["side"] == "BUY" else (px < ref)
    # Deterministic: the same costs give the same ledger.
    again_deps, again = go(ExecutionCosts(D("10"), D("50"), D("0.01")))
    assert again.state.head_hash == paid.state.head_hash
    assert free.state.head_hash != paid.state.head_hash


# --- cache and bar source --------------------------------------------------------------------------

def build(tmp_path, rows, sym="AAA"):
    cache.write(sym, rows, tmp_path)
    return HistoricalBarSource(WORLD.calendar, [sym], tmp_path)


def test_cache_round_trips(tmp_path):
    rows = [row(DAYS[0]), row(DAYS[1], "101.5", "102", "100", "101")]
    cache.write("AAA", rows, tmp_path)
    assert cache.read("AAA", tmp_path) == rows and cache.read("ZZZ", tmp_path) == []


def test_a_bar_is_invisible_until_its_session_has_closed(tmp_path):
    src = build(tmp_path, [row(DAYS[0]), row(DAYS[1]), row(DAYS[2])])
    s1 = WORLD.calendar.session(DAYS[1])
    assert [b.day for b in src.history("AAA", s1.close - timedelta(seconds=1))] == [DAYS[0]]
    assert [b.day for b in src.history("AAA", s1.close)] == [DAYS[0], DAYS[1]]
    assert src.bar("AAA", DAYS[1], s1.close - timedelta(seconds=1)) is None
    assert src.bar("AAA", DAYS[1], s1.close).day == DAYS[1]
    assert [b.day for b in src.history("AAA", s1.close, 1)] == [DAYS[1]]
    assert src.history("AAA", WORLD.calendar.session(DAYS[0]).open) == ()


def test_bad_rows_are_dropped_and_counted_not_repaired(tmp_path):
    saturday = date(2026, 9, 5)
    rows = [row(DAYS[0]), row(DAYS[1], "100", "99", "98", "100"), row(saturday), row(DAYS[3])]  # high < open; non-session
    q = build(tmp_path, rows).quality.per_symbol["AAA"]
    assert (q.rows, q.dropped_bad_ohlc, q.dropped_not_session) == (4, 1, 1)
    assert q.first == DAYS[0] and q.last == DAYS[3]


def test_missing_observations_are_measured_against_other_symbols_sessions(tmp_path):
    cache.write("AAA", [row(d) for d in DAYS[:6]], tmp_path)
    cache.write("BBB", [row(DAYS[0]), row(DAYS[1]), row(DAYS[4]), row(DAYS[5])], tmp_path)  # two sessions missing
    src = HistoricalBarSource(WORLD.calendar, ["AAA", "BBB"], tmp_path)
    q = src.quality.per_symbol
    assert q["AAA"].missing_sessions == 0
    assert q["BBB"].missing_sessions == 2 and q["BBB"].max_gap_sessions == 2


def test_splits_and_dividends_are_counted_in_the_audit(tmp_path):
    rows = [row(DAYS[0]), replace(row(DAYS[1]), split=D("4")), replace(row(DAYS[2]), dividend=D("0.5"))]
    q = build(tmp_path, rows).quality.per_symbol["AAA"]
    assert (q.splits, q.dividends) == (1, 1)


def test_float_noise_is_trimmed_to_four_decimals(tmp_path):
    src = build(tmp_path, [row(DAYS[0], "96.66000366210938", "97.1", "95.5", "96.2")])
    assert src.history("AAA", WORLD.calendar.session(DAYS[0]).close)[0].open == D("96.6600")


def test_the_replay_ledger_is_untouched_by_the_cost_hook():
    """Costs are folded into fill prices; the books still verify NAV against the ledger every session."""
    world = make_world()
    deps = replace(make_deps(world), costs=ExecutionCosts(D("25"), D("100"), D("0.02")))
    led = start(world, deps)
    run(world, deps, led, START_INDEX, START_INDEX + 30)  # raises LedgerError if any mark disagrees with the books
    replayed = Ledger(type(led.store)(led.store.read_all()))
    assert replayed.state.digest() == led.state.digest()
