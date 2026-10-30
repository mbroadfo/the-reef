"""Recovery, idempotency and look-ahead safety of the shared engine."""
from __future__ import annotations

import random
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tests.fixtures.hunter_scenario import START_INDEX, make_deps, make_world
from tests.hunter.conftest import run, start
from the_reef.engine.advance import EngineError, advance, next_session_to_advance
from the_reef.ledger.ledger import InMemoryEventStore, Ledger
from the_reef.market.bars import DailyBar, StaticBarSource

D = Decimal
WINDOW_END = START_INDEX + 24  # sessions 55..79 cover entries, rejections, stops and exits


class Crash(RuntimeError):
    pass


class CrashingStore(InMemoryEventStore):
    """Raises on the Nth append, as if the process died mid-session."""

    def __init__(self, crash_at: int | None) -> None:
        super().__init__()
        self.crash_at, self.count = crash_at, 0

    def append(self, event) -> None:
        self.count += 1
        if self.crash_at is not None and self.count == self.crash_at:
            raise Crash(f"crashed on append {self.count}")
        super().append(event)


def uninterrupted(world, last):
    deps = make_deps(world)
    led = start(world, deps)
    run(world, deps, led, START_INDEX, last)
    return led


# --- idempotency and ordering -------------------------------------------------------------------

def test_rerunning_a_completed_session_changes_nothing(world):
    deps = make_deps(world)
    led = start(world, deps)
    run(world, deps, led, START_INDEX, START_INDEX + 12)
    digest, n = led.state.digest(), len(led.store.read_all())
    again = advance(led, deps, world.days[START_INDEX + 12])
    assert again.appended == 0
    assert led.state.digest() == digest and len(led.store.read_all()) == n


def test_sessions_must_be_advanced_one_at_a_time_and_in_order(world):
    deps = make_deps(world)
    led = start(world, deps)
    run(world, deps, led, START_INDEX, START_INDEX + 2)
    with pytest.raises(EngineError, match="skips a session"):
        advance(led, deps, world.days[START_INDEX + 4])
    with pytest.raises(EngineError, match="before the last started"):
        advance(led, deps, world.days[START_INDEX])
    with pytest.raises(EngineError, match="not a trading session"):
        advance(led, deps, date(2026, 9, 7))  # Labor Day


def test_bootstrap_is_idempotent(world):
    deps = make_deps(world)
    led = start(world, deps)
    digest = led.state.digest()
    start(world, deps, led)
    assert led.state.digest() == digest


# --- recovery from an interrupted run ------------------------------------------------------------

def test_a_crash_at_any_append_resumes_to_exactly_the_uninterrupted_result(world):
    expected = uninterrupted(world, WINDOW_END)
    total = len(expected.store.read_all())
    crash_points = list(range(1, total))  # every append in the window, including bootstrap
    assert len(crash_points) > 100
    for crash_at in crash_points:
        store = CrashingStore(crash_at)
        led = Ledger(store)
        deps = make_deps(world)
        crashed = False
        try:
            start(world, deps, led)
            run(world, deps, led, START_INDEX, WINDOW_END)
        except Crash:
            crashed = True
        assert crashed, f"expected a crash at append {crash_at}"
        # Restart: a new process rebuilds from whatever the store durably holds, then carries on.
        revived = Ledger(InMemoryEventStore(store.read_all()))
        start(world, deps, revived)  # bootstrap is idempotent, so a crash before it finished is fine
        first = world.days.index(next_session_to_advance(revived, deps, world.days[START_INDEX]))
        run(world, deps, revived, first, WINDOW_END)
        assert revived.state.digest() == expected.state.digest(), f"diverged after crash at append {crash_at}"
        assert revived.state.head_hash == expected.state.head_hash


# --- no look-ahead ------------------------------------------------------------------------------

def test_decisions_up_to_a_session_do_not_depend_on_bars_after_it(world):
    k = START_INDEX + 30
    base = uninterrupted(world, k)

    rnd = random.Random(7)
    future = set(world.days[k + 1:])
    scrambled = []
    for symbol in world.bars.symbols():
        for day in sorted(world.bars._by_symbol[symbol]):  # noqa: SLF001 - fixture surgery
            b = world.bars._by_symbol[symbol][day]  # noqa: SLF001
            if day in future:
                f = D(str(rnd.uniform(0.3, 3.0)))
                b = DailyBar(symbol, day, (b.open * f).quantize(D("0.01")), (b.high * f * 2).quantize(D("0.01")),
                             (b.low * f / 2).quantize(D("0.01")), (b.close * f).quantize(D("0.01")), b.volume, b.source)
            scrambled.append(b)
    other = replace(make_deps(world), bars=StaticBarSource(scrambled, world.calendar))
    led = start(world, other)
    run(world, other, led, START_INDEX, k)
    assert led.state.digest() == base.state.digest() and led.state.head_hash == base.state.head_hash


def test_history_never_includes_a_session_that_has_not_closed(world):
    day = world.days[START_INDEX + 5]
    session = world.calendar.session(day)
    just_before = session.close - timedelta(seconds=1)
    at_close = session.close
    h_before = world.bars.history("HUNT", just_before)
    h_close = world.bars.history("HUNT", at_close)
    assert h_before[-1].day == world.days[START_INDEX + 4]
    assert h_close[-1].day == day
    assert world.bars.bar("HUNT", day, just_before) is None
    assert world.bars.bar("HUNT", day, at_close) is not None
    assert all(b.day <= day for b in h_close)


def test_the_open_print_is_stamped_at_the_open_and_the_close_at_the_close(world):
    day = world.days[START_INDEX + 5]
    s = world.calendar.session(day)
    assert world.bars.official_open("HUNT", s).as_of == s.open
    assert world.bars.official_close("HUNT", s).as_of == s.close


def test_a_bar_on_a_non_session_day_is_refused(world):
    bar = DailyBar("X", date(2026, 9, 7), D(1), D(1), D(1), D(1), 1, "t")
    with pytest.raises(ValueError, match="not a session"):
        StaticBarSource([bar], world.calendar)


def test_daily_bar_rejects_inconsistent_ohlc():
    with pytest.raises(ValueError):
        DailyBar("X", date(2026, 9, 8), D(10), D(9), D(8), D(10), 1, "t")
    with pytest.raises(ValueError):
        DailyBar("X", date(2026, 9, 8), D(10), D(11), D(0), D(10), 1, "t")


def test_a_holding_without_a_valid_close_is_unmarked_and_the_book_untrusted(world):
    """E-6: a missing close is never papered over with an old price."""
    deps = make_deps(world)
    led = start(world, deps)
    run(world, deps, led, START_INDEX, START_INDEX + 9)
    held = [s for s, p in led.state.epoch().sleeves["hunter"].positions.items()]
    assert held, "scenario should be holding something by now"
    sym = held[0]
    nxt = world.days[START_INDEX + 10]
    # Rebuild the data without that symbol's bar on the next session.
    kept = [b for s in world.bars.symbols() for b in world.bars._by_symbol[s].values()  # noqa: SLF001
            if not (b.symbol == sym and b.day == nxt)]
    other = replace(deps, bars=StaticBarSource(kept, world.calendar))
    report = advance(led, other, nxt)
    assert any("UNMARKED" in n.detail for n in report.notes)
    mark = [e for e in led.store.read_all() if e.draft.kind.value == "SESSION_MARKED"][-1].draft.payload
    assert sym in mark["unmarked"] and sym not in mark["marks"]


class SpyBars(StaticBarSource):
    """Counts the data a session reads, to prove which steps ran."""

    def __init__(self, inner: StaticBarSource, calendar) -> None:
        self.__dict__.update(inner.__dict__)
        self.reads: list[tuple[str, date]] = []

    def bar(self, symbol, day, as_of):
        self.reads.append(("bar", day))
        return super().bar(symbol, day, as_of)

    def official_open(self, symbol, session):
        self.reads.append(("open", session.day))
        return super().official_open(symbol, session)

    def official_close(self, symbol, session):
        self.reads.append(("close", session.day))
        return super().official_close(symbol, session)


def test_finishing_a_marked_session_only_reruns_the_decision_step(world):
    """After the mark, fills, stops and the valuation are history; re-running them could apply
    stops raised at this close to the session that already happened."""
    deps = make_deps(world)
    led = start(world, deps)
    run(world, deps, led, START_INDEX, START_INDEX + 20)
    events = list(led.store.read_all())
    half = Ledger(InMemoryEventStore(events[:-1]))  # drop the final SESSION_CLOSED
    day = world.days[START_INDEX + 20]
    assert half.state.epoch().last_marked == day.isoformat() and half.state.epoch().last_completed != day.isoformat()
    spy = SpyBars(world.bars, world.calendar)
    advance(half, replace(deps, bars=spy), day)
    session_reads = [r for r in spy.reads if r[1] == day]
    assert not any(kind in ("open", "close") for kind, _ in session_reads)  # no fills, no marking
    assert half.state.digest() == led.state.digest()


def test_an_order_for_a_later_session_is_not_filled_early(world):
    from the_reef.ledger import events as ev

    deps = make_deps(world)
    led = start(world, deps)
    run(world, deps, led, START_INDEX, START_INDEX)
    nxt, later = world.days[START_INDEX + 1], world.days[START_INDEX + 3]
    at = world.calendar.session(world.days[START_INDEX]).close + timedelta(minutes=2)
    led.append(ev.order_queued(deps.epoch_id, at, sleeve_id="hunter", order_id="future", symbol="FLATA", intent="open",
                               requested_shares=5, stop_price=D("30"), fill_session=later, ref_price=D("40"), sector=None))
    advance(led, deps, nxt)
    assert led.state.epoch().orders["hunter:future"].status.value == "QUEUED"
    run(world, deps, led, START_INDEX + 2, START_INDEX + 3)
    assert led.state.epoch().orders["hunter:future"].status.value != "QUEUED"
