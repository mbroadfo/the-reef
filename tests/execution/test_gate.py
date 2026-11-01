from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tests.conftest import ny
from tests.fixtures.market import standard_actions, standard_master
from the_reef.execution.gate import (
    GateCode,
    GatePorts,
    OrderIntent,
    fill_at_open,
    immediate_fill_allowed,
    queue_order,
)
from the_reef.market.instruments import (
    InstrumentRecord,
    InstrumentStatus,
    Intent,
    StaticInstrumentMaster,
    TradabilityCode,
)
from the_reef.market.quotes import Quote, QuoteIssue, QuoteKind
from the_reef.risk.engine import PortfolioView, PositionView, RejectCode
from the_reef.risk.limits import RiskLimits

D = Decimal


def order(symbol="AAPL", intent=Intent.OPEN, decided=None, ref="100", stop="95", **kw):
    return OrderIntent(
        pod_id="test", symbol=symbol, intent=intent, decided_at=decided or ny(2026, 7, 2, 16, 5),
        ref_price=D(ref), stop_price=D(stop) if stop is not None else None, sector="Technology", **kw,
    )


def book(cash="10000", positions=(), trusted=True, nav=None, prior="10000"):
    positions = tuple(positions)
    invested = sum((p.value for p in positions), D("0"))
    return PortfolioView(D(nav) if nav else D(cash) + invested, D(cash), D(prior), D("10000"), positions, trusted)


def open_print(ports, day, price="100", **kw):
    s = ports.calendar.session(day)
    base = dict(symbol="AAPL", price=D(price), as_of=s.open, source="test", kind=QuoteKind.OFFICIAL_OPEN)
    base.update(kw)
    return Quote(**base)


# --- queue_order: decide at the close, fill at the next valid open ---------------------------

@pytest.mark.parametrize(
    "decided, fill_day",
    [
        (ny(2026, 7, 1, 16, 5), date(2026, 7, 2)),
        (ny(2026, 7, 2, 16, 5), date(2026, 7, 6)),  # 07-03 is a holiday, 07-04/05 a weekend
        (ny(2026, 7, 4, 10, 0), date(2026, 7, 6)),
        (ny(2026, 7, 2, 8, 0), date(2026, 7, 2)),  # before the open: today's open
        (ny(2026, 11, 27, 13, 5), date(2026, 11, 30)),  # after the early close
    ],
)
def test_orders_queue_to_the_next_valid_open(ports, decided, fill_day):
    d = queue_order(ports, order(decided=decided))
    assert d.accepted and d.queued is not None
    assert d.queued.fill_session == fill_day
    assert d.queued.fill_not_before == ports.calendar.session(fill_day).open
    assert d.queued.fill_not_before > decided


def test_symbol_is_normalized_and_invalid_symbols_are_rejected(ports):
    assert queue_order(ports, order(symbol=" aapl ")).queued.symbol == "AAPL"
    for bad in ("", "$$$", "A B", "12345"):
        d = queue_order(ports, order(symbol=bad))
        assert not d.accepted and d.code is GateCode.INVALID_SYMBOL


def test_open_and_add_require_an_invalidation_price(ports):
    for intent in (Intent.OPEN, Intent.ADD):
        d = queue_order(ports, order(intent=intent, stop=None))
        assert not d.accepted and d.code is GateCode.RISK_REJECTED
    assert queue_order(ports, order(intent=Intent.CLOSE, stop=None)).accepted


@pytest.mark.parametrize(
    "symbol, code",
    [
        ("SEM", TradabilityCode.ACQUIRED),
        ("GONE", TradabilityCode.DELISTED),
        ("HALT", TradabilityCode.HALTED),
        ("ZZZZ", TradabilityCode.UNKNOWN_SYMBOL),
        ("SPCX", TradabilityCode.INSUFFICIENT_HISTORY),
    ],
)
def test_untradable_instruments_never_reach_the_queue(ports, symbol, code):
    d = queue_order(ports, order(symbol=symbol, decided=ny(2026, 7, 2, 16, 5)))
    assert not d.accepted and d.code is GateCode.INSTRUMENT_NOT_TRADABLE and d.tradability is code and d.queued is None


def test_calendar_past_its_range_fails_closed(ports):
    d = queue_order(ports, order(decided=ny(2026, 12, 31, 17, 0)))
    assert not d.accepted and d.code is GateCode.CALENDAR_UNAVAILABLE
    d = queue_order(ports, order(decided=ny(2027, 3, 1, 10, 0)))
    assert not d.accepted and d.code is GateCode.CALENDAR_UNAVAILABLE


# --- immediate fills (the legacy path) -------------------------------------------------------

@pytest.mark.parametrize(
    "when, code",
    [
        (ny(2026, 7, 2, 10, 0), GateCode.ACCEPTED),
        (ny(2026, 7, 2, 8, 30), GateCode.OUTSIDE_REGULAR_HOURS),
        (ny(2026, 7, 2, 16, 0), GateCode.OUTSIDE_REGULAR_HOURS),
        (ny(2026, 7, 3, 10, 0), GateCode.MARKET_CLOSED_HOLIDAY),
        (ny(2026, 7, 4, 10, 0), GateCode.MARKET_CLOSED_WEEKEND),
        (ny(2026, 11, 27, 14, 0), GateCode.OUTSIDE_REGULAR_HOURS),  # after the 1pm early close
        (ny(2027, 3, 1, 10, 0), GateCode.CALENDAR_UNAVAILABLE),
    ],
)
def test_immediate_fill_only_inside_a_regular_session(ports, when, code):
    assert immediate_fill_allowed(ports, when).code is code


# --- fill_at_open ----------------------------------------------------------------------------

def test_fill_uses_the_official_open_and_risk_sizing(ports):
    q = queue_order(ports, order(decided=ny(2026, 7, 2, 16, 5))).queued
    d = fill_at_open(ports, q, open_print(ports, q.fill_session, "100"), book(), D(1666))
    assert d.accepted and d.shares == 10 and d.risk is not None  # 0.5% of 10k / $5 risk = 10


@pytest.mark.parametrize(
    "print_kw, issue",
    [
        (dict(kind=QuoteKind.LAST), QuoteIssue.WRONG_KIND),
        (dict(as_of=None), QuoteIssue.NO_TIMESTAMP),
        (dict(price=D("0")), QuoteIssue.NON_POSITIVE_PRICE),
        (dict(source=None), QuoteIssue.NO_SOURCE),
    ],
)
def test_no_fill_without_a_valid_open_print(ports, print_kw, issue):
    q = queue_order(ports, order()).queued
    d = fill_at_open(ports, q, open_print(ports, q.fill_session, **print_kw), book(), D(1666))
    assert not d.accepted and d.code is GateCode.NO_VALID_OPEN_PRINT and issue in d.quote_issues


def test_a_stale_print_from_the_previous_session_is_not_a_fill_price(ports):
    q = queue_order(ports, order(decided=ny(2026, 7, 2, 16, 5))).queued  # fills 07-06
    prior_close = ports.calendar.session(date(2026, 7, 2)).close
    d = fill_at_open(ports, q, open_print(ports, q.fill_session, as_of=prior_close), book(), D(1666))
    assert not d.accepted and d.code is GateCode.NO_VALID_OPEN_PRINT
    assert fill_at_open(ports, q, None, book(), D(1666)).code is GateCode.NO_VALID_OPEN_PRINT


def test_instrument_that_became_untradable_after_queueing_is_refused_at_fill(ports):
    q = queue_order(ports, order(decided=ny(2026, 7, 2, 16, 5))).queued
    halted = InstrumentRecord("AAPL", "NASDAQ", InstrumentStatus.HALTED, date(1980, 12, 12), None, "Technology", "t", datetime(2020, 1, 1, tzinfo=timezone.utc))
    later = replace(ports, instruments=StaticInstrumentMaster([halted]))
    d = fill_at_open(later, q, open_print(ports, q.fill_session), book(), D(1666))
    assert not d.accepted and d.code is GateCode.INSTRUMENT_NOT_TRADABLE and d.tradability is TradabilityCode.HALTED


def test_risk_can_reject_at_fill_time(ports):
    q = queue_order(ports, order(decided=ny(2026, 7, 2, 16, 5))).queued
    paused = book(cash="9700", nav="9700", prior="10000")
    d = fill_at_open(ports, q, open_print(ports, q.fill_session), paused, D(1666))
    assert not d.accepted and d.code is GateCode.RISK_REJECTED and d.risk.reasons == (RejectCode.DAILY_LOSS_PAUSE,)


def test_exit_orders_fill_even_when_entries_are_paused(ports):
    held = [PositionView("AAPL", 10, D(100), "Technology")]
    paused = book(cash="8500", positions=held, nav="9500", prior="10000", trusted=False)
    q = queue_order(ports, order(intent=Intent.CLOSE, stop=None, requested_shares=10)).queued
    d = fill_at_open(ports, q, open_print(ports, q.fill_session), paused, D(0))
    assert d.accepted and d.shares == 10


def test_fill_session_that_is_not_a_session_is_refused(ports):
    q = queue_order(ports, order()).queued
    bad = replace(q, fill_session=date(2026, 7, 3))
    assert fill_at_open(ports, bad, None, book(), D(0)).code is GateCode.MARKET_CLOSED_HOLIDAY
