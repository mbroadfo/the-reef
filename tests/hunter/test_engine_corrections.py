"""Regression tests for two execution defects found in review of the first Hunter slice.

1. Stops that fire on the same day carry different event times (gap = the open, touch = the
   close) and must reach the append-only ledger in time order, whatever the sleeve/symbol order.
2. Risk checks must use the ledger's validated session marks. A holding the session could not
   mark makes the book untrusted: new exposure is blocked, exits are not, at the decision and at
   the next open.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from tests.fixtures.hunter_scenario import START_INDEX, make_deps, make_world
from tests.hunter.test_engine_safety import Crash, CrashingStore
from the_reef.allocation.d0 import D0Config
from the_reef.engine import advance as eng
from the_reef.engine.advance import NoteKind, SleeveSpec, advance, bootstrap, next_session_to_advance
from the_reef.ledger import events as ev
from the_reef.ledger.events import EventKind, Side
from the_reef.ledger.ledger import InMemoryEventStore, Ledger
from the_reef.market.bars import DailyBar, StaticBarSource
from the_reef.market.instruments import Intent
from the_reef.strategy.base import Proposal, Review, StrategyContext

D = Decimal
WORLD = make_world()
DAYS = WORLD.days[START_INDEX:START_INDEX + 4]
DAY0, DAY1, DAY2 = DAYS[0], DAYS[1], DAYS[2]


class Scripted:
    """Proposes an entry in ``enter`` on ``enter_on`` and exits ``exit_syms`` when held. No LLM, no data."""

    spec_hash = "scripted"

    def __init__(self, sid, enter=None, enter_on=None, exit_syms=()):
        self.strategy_id, self.enter, self.enter_on, self.exit_syms = sid, enter, enter_on, tuple(exit_syms)

    def _last(self, ctx, sym):
        return ctx.bars[sym][-1].close

    def propose(self, ctx: StrategyContext):
        if self.enter and ctx.session_day == self.enter_on and self.enter not in ctx.holdings and self.enter not in ctx.blocked:
            px = self._last(ctx, self.enter)
            return [Proposal(self.enter, Intent.OPEN, D("1"), px, px * D("0.90"), "scripted entry")]
        return []

    def review(self, ctx: StrategyContext):
        exits = [Proposal(s, Intent.CLOSE, D("1"), self._last(ctx, s), None, "scripted exit")
                 for s in self.exit_syms if s in ctx.holdings and ctx.session_day == self.enter_on]
        return Review(exits=tuple(exits))


def bar(sym, day, o, low, c, high=None):
    return DailyBar(sym, day, D(o), D(high or max(o, c, 101)), D(low), D(c), 100_000, "test")


def flat(sym, day):
    return bar(sym, day, 100, 99, 100)


def deps_for(bars, sleeves, universe=()):
    base = make_deps(WORLD)
    weights = {s.sleeve_id: D("0.40") for s in sleeves}
    return replace(base, bars=StaticBarSource(bars, WORLD.calendar), sleeves=sleeves, universe=universe,
                   d0=D0Config(weights, max_new_per_session=2))


def buy(led, deps, sid, sym, shares, stop, price=D("100")):
    close = deps.calendar.session(DAY0).close
    led.append(ev.fill(deps.epoch_id, close + timedelta(minutes=2), sleeve_id=sid, order_id=f"seed:{sym}", symbol=sym,
                       side=Side.BUY, shares=shares, price=price, session_day=DAY0, stop_price=D(stop)))


# --- 1. chronological stop execution --------------------------------------------------------------

STOP_BOOKS = {"alpha": [("FLATA", 95), ("FLATB", 95)], "beta": [("FLATC", 95), ("HUNT", 95), ("TRND", 80)]}
DAY1_BARS = [
    bar("FLATA", DAY1, 100, 94, 96),   # alpha: touch  -> at the stop, stamped at the close
    bar("FLATB", DAY1, 90, 88, 91),    # alpha: gap    -> at the open
    bar("FLATC", DAY1, 92, 90, 93),    # beta : gap
    bar("HUNT", DAY1, 100, 94, 97),    # beta : touch
    bar("TRND", DAY1, 100, 98, 101),   # beta : untouched
]


def stops_deps():
    syms = [s for book in STOP_BOOKS.values() for s, _ in book]
    bars = [flat(s, d) for s in syms for d in (DAY0, DAY2)] + DAY1_BARS
    return deps_for(bars, [SleeveSpec(sid, Scripted(sid)) for sid in STOP_BOOKS])


def build_stops(led, deps, last=DAY1):
    bootstrap(led, deps, deps.calendar.session(DAY0).open - timedelta(hours=1))
    advance(led, deps, DAY0)
    for sid, book in STOP_BOOKS.items():
        for sym, stop in book:
            buy(led, deps, sid, sym, 10, stop)
    resume = next_session_to_advance(led, deps, DAY0)
    for day in [d for d in DAYS if resume <= d <= last]:
        advance(led, deps, day)


def stop_fills(led):
    return [e for e in led.store.read_all()
            if e.draft.kind is EventKind.FILL and str(e.draft.payload["order_id"]).startswith("stop:")]


def test_gap_and_touch_stops_on_one_day_are_appended_in_time_order_across_sleeves():
    deps = stops_deps()
    led = Ledger()
    build_stops(led, deps)
    fills = stop_fills(led)
    assert [(f.draft.payload["sleeve_id"], f.draft.payload["symbol"]) for f in fills] == [
        ("alpha", "FLATB"), ("beta", "FLATC"),   # gaps, at the open
        ("alpha", "FLATA"), ("beta", "HUNT"),    # touches, at the close
    ]
    times = [f.draft.occurred_at for f in fills]
    assert times == sorted(times)
    prices = {f.draft.payload["symbol"]: f.draft.payload["price"] for f in fills}
    assert prices == {"FLATB": "90", "FLATC": "92", "FLATA": "95", "HUNT": "95"}
    ep = led.state.epoch()
    assert set(ep.sleeves["beta"].positions) == {"TRND"} and not ep.sleeves["alpha"].positions
    assert led.state.epoch().last_completed == DAY1.isoformat()


def test_stop_execution_order_is_stable_when_holdings_are_reversed():
    """The result depends on event time, not on dict or sleeve iteration order."""
    deps = stops_deps()
    led = Ledger()
    build_stops(led, deps)
    deps_r = replace(deps, sleeves=list(reversed(deps.sleeves)))
    rev = Ledger()
    build_stops(rev, deps_r)
    assert led.state.digest() == rev.state.digest()


def test_stops_that_fire_together_survive_a_crash_at_every_append():
    deps = stops_deps()
    expected = Ledger()
    build_stops(expected, deps)
    total = len(expected.store.read_all())
    stop_idx = [i for i, e in enumerate(expected.store.read_all(), 1)
                if e.draft.kind is EventKind.FILL and str(e.draft.payload["order_id"]).startswith("stop:")]
    assert len(stop_idx) == 4
    for crash_at in range(1, total):
        store = CrashingStore(crash_at)
        try:
            build_stops(Ledger(store), deps)
        except Crash:
            pass
        else:
            raise AssertionError(f"no crash at append {crash_at}")
        revived = Ledger(InMemoryEventStore(store.read_all()))
        build_stops(revived, deps)
        assert revived.state.digest() == expected.state.digest(), f"diverged after crash at append {crash_at}"
        assert revived.state.head_hash == expected.state.head_hash
    assert min(stop_idx) < total  # the sweep covered the points between the individual stop events


# --- 2. unmarked positions and risk enforcement ---------------------------------------------------

def risk_deps(with_h_bar_on_day1: bool, exit_h: bool = False):
    bars = [flat(s, d) for s in ("FLATA", "FLATB") for d in (DAY0, DAY2)] + [flat("FLATB", DAY1)]
    if with_h_bar_on_day1:
        bars.append(flat("FLATA", DAY1))
    strat = Scripted("alpha", enter="FLATB", enter_on=DAY1, exit_syms=("FLATA",) if exit_h else ())
    return deps_for(bars, [SleeveSpec("alpha", strat)], universe=("FLATA", "FLATB"))


def run_risk(deps, last=DAY1):
    led = Ledger()
    bootstrap(led, deps, deps.calendar.session(DAY0).open - timedelta(hours=1))
    advance(led, deps, DAY0)
    buy(led, deps, "alpha", "FLATA", 10, "90")
    for day in DAYS[1:DAYS.index(last) + 1]:
        advance(led, deps, day)
    return led


def of_kind(led, kind):
    return [e.draft.payload for e in led.store.read_all() if e.draft.kind is kind]


def test_control_a_fully_marked_book_may_open_a_new_position():
    led = run_risk(risk_deps(with_h_bar_on_day1=True))
    assert [o["symbol"] for o in of_kind(led, EventKind.ORDER_QUEUED)] == ["FLATB"]
    assert led.state.epoch().last_unmarked == frozenset()


def test_a_missing_close_is_not_replaced_by_an_earlier_close_when_sizing_new_exposure():
    led = run_risk(risk_deps(with_h_bar_on_day1=False))
    ep = led.state.epoch()
    assert ep.last_unmarked == frozenset({"FLATA"}) and "FLATA" not in ep.last_mark_prices
    assert of_kind(led, EventKind.ORDER_QUEUED) == []
    rejected = of_kind(led, EventKind.ORDER_REJECTED)
    assert len(rejected) == 1 and rejected[0]["stage"] == "DECISION" and "BOOK_UNTRUSTED" in rejected[0]["code"]


def test_untrusted_book_blocks_entries_at_the_next_open():
    deps = risk_deps(with_h_bar_on_day1=False)
    led = run_risk(deps)
    # An entry queued while the book was still trusted meets the same untrusted mark at the open.
    decided = deps.calendar.session(DAY1).close + eng.DECISION_DELAY
    led.append(ev.order_queued(deps.epoch_id, decided, sleeve_id="alpha", order_id="early:FLATB", symbol="FLATB",
                               intent="open", requested_shares=5, stop_price=D("90"), fill_session=DAY2,
                               ref_price=D("100"), sector=None))
    advance(led, deps, DAY2)
    rejects = [o for o in of_kind(led, EventKind.ORDER_REJECTED) if o["stage"] == "FILL"]
    assert [(o["symbol"], "BOOK_UNTRUSTED" in o["code"]) for o in rejects] == [("FLATB", True)]
    assert "FLATB" not in led.state.epoch().sleeves["alpha"].positions


def test_an_untrusted_book_does_not_block_exits_at_the_decision_or_the_open():
    deps = risk_deps(with_h_bar_on_day1=False, exit_h=True)
    led = run_risk(deps)
    queued = of_kind(led, EventKind.ORDER_QUEUED)
    assert [(o["symbol"], o["intent"]) for o in queued] == [("FLATA", "close")]
    advance(led, deps, DAY2)
    sells = [o for o in of_kind(led, EventKind.FILL) if o["side"] == "SELL"]
    assert [(o["symbol"], o["shares"]) for o in sells] == [("FLATA", 10)]
    assert not led.state.epoch().sleeves["alpha"].positions


def test_marks_from_any_other_session_are_untrusted():
    led = run_risk(risk_deps(with_h_bar_on_day1=True))
    ep, deps = led.state.epoch(), risk_deps(True)
    at = deps.calendar.session(DAY1).close
    assert eng._risk_view(ep, deps, at, DAY1, marked_day=DAY1.isoformat()).book_trusted
    stale = eng._risk_view(ep, deps, at, DAY1, marked_day=DAY0.isoformat())
    assert not stale.book_trusted


def test_the_report_notes_the_unmarked_holding():
    deps = risk_deps(with_h_bar_on_day1=False)
    led = Ledger()
    bootstrap(led, deps, deps.calendar.session(DAY0).open - timedelta(hours=1))
    advance(led, deps, DAY0)
    buy(led, deps, "alpha", "FLATA", 10, "90")
    report = advance(led, deps, DAY1)
    assert any(n.kind is NoteKind.MARKED and "UNMARKED FLATA" in n.detail for n in report.notes)
    assert any(n.kind is NoteKind.DECISION_REJECTED and "BOOK_UNTRUSTED" in n.detail for n in report.notes)
