"""Regression tests for the Reef 1.0 execution-audit defects (E-1, E-2, E-5, E-9).

Each test replays the *shape* of the original failure: the timestamp, symbol and situation
that 1.0 mishandled. Only timestamps and symbols are used; no prices, amounts or P&L from the
private record. They must keep failing if the guard they protect is removed.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from tests.conftest import ny
from tests.fixtures.market import SEM_EVIDENCE, standard_actions
from the_reef.execution.gate import (
    GateCode,
    OrderIntent,
    fill_at_open,
    immediate_fill_allowed,
    queue_order,
)
from the_reef.market.calendar import TimePhase, classify
from the_reef.market.instruments import Intent, TradabilityCode, check_tradable, settlements_due
from the_reef.market.quotes import MarkStatus, Quote, QuoteIssue, QuoteKind, book_trust, mark_close, validate_quote
from the_reef.risk.engine import PortfolioView, PositionView, RejectCode, evaluate_entry, evaluate_exit
from the_reef.risk.limits import RiskLimits

D = Decimal


def buy(symbol, decided, stop="90"):
    return OrderIntent("regression", symbol, Intent.OPEN, decided, D("100"), D(stop), "Technology")


def test_e1_after_close_fill_is_refused_and_the_order_waits_for_the_next_open(ports):
    """E-1: 1.0 filled a buy at 20:07 ET on 2026-06-30, after the 16:00 close."""
    trade_time = datetime.fromisoformat("2026-07-01T00:07:15+00:00")  # 20:07 ET on 06-30
    assert classify(ports.calendar, trade_time).phase is TimePhase.AFTER_CLOSE
    assert immediate_fill_allowed(ports, trade_time).code is GateCode.OUTSIDE_REGULAR_HOURS

    queued = queue_order(ports, buy("AAPL", trade_time)).queued
    assert queued is not None
    assert queued.fill_session == date(2026, 7, 1)
    assert queued.fill_not_before == datetime(2026, 7, 1, 13, 30, tzinfo=timezone.utc)  # 09:30 ET, EDT


def test_e2_holiday_fill_is_refused_and_the_order_waits_for_the_next_real_session(ports):
    """E-2: 1.0 filled a buy at 09:35 ET on Friday 2026-07-03, when NYSE was closed."""
    trade_time = datetime.fromisoformat("2026-07-03T13:35:49+00:00")
    assert classify(ports.calendar, trade_time).phase is TimePhase.HOLIDAY
    assert immediate_fill_allowed(ports, trade_time).code is GateCode.MARKET_CLOSED_HOLIDAY

    queued = queue_order(ports, buy("FIZZ", trade_time)).queued
    assert queued is not None and queued.fill_session == date(2026, 7, 6)  # Monday; the weekend is skipped


def test_e5_a_price_without_timestamp_or_source_is_not_a_price(ports):
    """E-5: 1.0 used a bare last_price with no timestamp, source or validity."""
    bare = Quote("AAPL", D("16.51"), None, None, QuoteKind.LAST)  # what get_price() effectively returned
    now = datetime(2026, 7, 6, 15, 0, tzinfo=timezone.utc)
    result = validate_quote(bare, symbol="AAPL", now=now)
    assert not result.valid and {QuoteIssue.NO_TIMESTAMP, QuoteIssue.NO_SOURCE} <= set(result.issues)

    # A failed fetch used to be swallowed and the previous mark kept. Now it is UNMARKED, with no price.
    session = ports.calendar.session(date(2026, 7, 6))
    failed = mark_close(None, symbol="AAPL", session=session)
    assert failed.status is MarkStatus.UNMARKED and failed.price is None


def test_e5_e6_an_unmarkable_holding_makes_the_book_untrusted_and_blocks_new_exposure(ports):
    """E-6: an unmarkable position sat at cost for months while the book kept trading."""
    session = ports.calendar.session(date(2026, 7, 6))
    marks = [mark_close(None, symbol="HELD", session=session)]
    trust = book_trust(marks)
    assert not trust.trusted and trust.unmarked == ("HELD",)

    portfolio = PortfolioView(D(10000), D(8000), D(10000), D(10000), (PositionView("HELD", 10, D(200), None),), trust.trusted)
    entry = evaluate_entry(
        symbol="AAPL", sector="Technology", ref_price=D(100), stop_price=D(95), sleeve_cash=D(1666),
        portfolio=portfolio, limits=RiskLimits(),
    )
    assert not entry.approved and entry.reasons == (RejectCode.BOOK_UNTRUSTED,)
    assert evaluate_exit(symbol="HELD", requested_shares=10, portfolio=portfolio).approved  # exits stay open


def test_e9_a_buy_of_an_acquired_and_delisted_stock_is_refused(ports):
    """E-9: 1.0 recorded a buy of SEM at 10:20 ET on 2026-07-02, the day after its cash
    acquisition closed and the stock stopped trading (SEC 8-K 0001104659-26-079643)."""
    trade_time = datetime.fromisoformat("2026-07-02T14:20:29+00:00")
    assert classify(ports.calendar, trade_time).phase is TimePhase.REGULAR  # the market was open, SEM was not

    direct = check_tradable("SEM", date(2026, 7, 2), ports.instruments, ports.actions, ports.calendar, intent=Intent.OPEN, as_of=trade_time)
    assert not direct.ok and direct.code is TradabilityCode.ACQUIRED and direct.evidence == SEM_EVIDENCE

    gate = queue_order(ports, buy("SEM", trade_time))
    assert not gate.accepted and gate.code is GateCode.INSTRUMENT_NOT_TRADABLE
    assert gate.tradability is TradabilityCode.ACQUIRED and gate.queued is None


def test_e9_while_the_deal_is_pending_new_positions_are_blocked_too(ports):
    day = date(2026, 6, 22)  # before the close; price pinned near the deal price
    r = check_tradable("SEM", day, ports.instruments, ports.actions, ports.calendar, intent=Intent.OPEN, as_of=ny(2026, 6, 22, 9, 0))
    assert not r.ok and r.code is TradabilityCode.PENDING_CASH_DEAL


def test_e9_a_held_name_converts_to_cash_from_the_filing_not_a_quote():
    """A holder of SEM receives the filed $16.50 per share on the effective date (I-5)."""
    [event] = settlements_due({"SEM": 100}, standard_actions(), date(2026, 7, 1), holder="sleeve-a", as_of=ny(2026, 7, 1, 9, 0))
    assert event.cash == D("1650.00") and event.effective == date(2026, 7, 1)


def test_e9_even_a_queued_order_is_refused_at_fill_if_the_name_is_gone(ports):
    """Defence in depth: an order queued before a delisting must not fill after it."""
    from dataclasses import replace

    from the_reef.market.instruments import InstrumentRecord, InstrumentStatus, StaticInstrumentMaster

    queued = queue_order(ports, buy("AAPL", ny(2026, 7, 1, 16, 5))).queued
    assert queued is not None
    gone = InstrumentRecord("AAPL", "NASDAQ", InstrumentStatus.DELISTED, date(1980, 12, 12), date(2026, 7, 1), None, "t", datetime(2020, 1, 1, tzinfo=timezone.utc))
    later = replace(ports, instruments=StaticInstrumentMaster([gone]))
    session = ports.calendar.session(queued.fill_session)
    open_print = Quote("AAPL", D("100"), session.open, "t", QuoteKind.OFFICIAL_OPEN)
    d = fill_at_open(later, queued, open_print, PortfolioView(D(10000), D(10000), D(10000), D(10000)), D(1666))
    assert not d.accepted and d.code is GateCode.INSTRUMENT_NOT_TRADABLE


def test_e9_gate_uses_knowledge_at_decision_time_not_hindsight(ports):
    """Point in time: the same order is judged on what was public when it was decided."""
    from dataclasses import replace as _replace

    from tests.fixtures.market import SEM_DEAL
    from the_reef.market.instruments import StaticCorporateActions

    decided = ny(2026, 6, 22, 16, 5)
    known = queue_order(ports, buy("SEM", decided))
    assert known.tradability is TradabilityCode.PENDING_CASH_DEAL

    hindsight_free = _replace(
        ports, actions=StaticCorporateActions([_replace(SEM_DEAL, known_at=ny(2026, 6, 30, 9, 0))])
    )
    assert queue_order(hindsight_free, buy("SEM", decided)).accepted  # deal not yet public that day
    late = queue_order(hindsight_free, buy("SEM", ny(2026, 7, 1, 16, 5)))
    assert not late.accepted and late.tradability is TradabilityCode.ACQUIRED
