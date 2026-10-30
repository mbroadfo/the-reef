from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from the_reef.market.quotes import (
    MarkStatus,
    Quote,
    QuoteIssue,
    QuoteKind,
    book_trust,
    mark_close,
    validate_fill_quote,
    validate_quote,
)

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=timezone.utc)


def q(**kw):
    base = dict(symbol="AAPL", price=Decimal("10"), as_of=NOW - timedelta(minutes=1), source="test", kind=QuoteKind.LAST)
    base.update(kw)
    return Quote(**base)


def test_good_quote_is_valid():
    assert validate_quote(q(), symbol="AAPL", now=NOW).valid


@pytest.mark.parametrize(
    "quote, issue",
    [
        (None, QuoteIssue.MISSING),
        (q(symbol="MSFT"), QuoteIssue.WRONG_SYMBOL),
        (q(price=None), QuoteIssue.NON_POSITIVE_PRICE),
        (q(price=Decimal("0")), QuoteIssue.NON_POSITIVE_PRICE),
        (q(price=Decimal("-1")), QuoteIssue.NON_POSITIVE_PRICE),
        (q(as_of=None), QuoteIssue.NO_TIMESTAMP),
        (q(as_of=datetime(2026, 7, 6, 14, 59)), QuoteIssue.NO_TIMESTAMP),  # naive
        (q(source=None), QuoteIssue.NO_SOURCE),
        (q(as_of=NOW + timedelta(minutes=1)), QuoteIssue.FUTURE_TIMESTAMP),
        (q(as_of=NOW - timedelta(minutes=21)), QuoteIssue.STALE),
        (q(as_of=NOW - timedelta(days=30)), QuoteIssue.STALE),
    ],
)
def test_invalid_quotes(quote, issue):
    result = validate_quote(quote, symbol="AAPL", now=NOW)
    assert not result.valid and issue in result.issues


def test_required_kind_is_enforced():
    result = validate_quote(q(), symbol="AAPL", now=NOW, required_kind=QuoteKind.OFFICIAL_OPEN)
    assert QuoteIssue.WRONG_KIND in result.issues


def open_print(session, **kw):
    base = dict(symbol="AAPL", price=Decimal("10"), as_of=session.open, source="test", kind=QuoteKind.OFFICIAL_OPEN)
    base.update(kw)
    return Quote(**base)


def test_fill_quote_must_be_the_official_open_of_that_session(calendar):
    session = calendar.session(date(2026, 7, 6))
    assert validate_fill_quote(open_print(session), symbol="AAPL", session=session).valid
    near = open_print(session, as_of=session.open + timedelta(minutes=4))
    assert validate_fill_quote(near, symbol="AAPL", session=session).valid
    for bad in (
        open_print(session, kind=QuoteKind.LAST),
        open_print(session, as_of=session.open + timedelta(minutes=11)),
        open_print(session, as_of=session.open - timedelta(days=1)),  # yesterday's close is not today's open
        open_print(session, as_of=None),
        open_print(session, price=Decimal("0")),
    ):
        assert not validate_fill_quote(bad, symbol="AAPL", session=session).valid
    assert not validate_fill_quote(None, symbol="AAPL", session=session).valid


def test_failed_mark_is_unmarked_and_never_reuses_a_price(calendar):
    session = calendar.session(date(2026, 7, 6))
    good = Quote("AAPL", Decimal("12"), session.close, "test", QuoteKind.OFFICIAL_CLOSE)
    ok = mark_close(good, symbol="AAPL", session=session)
    assert ok.status is MarkStatus.MARKED and ok.price == Decimal("12")
    for bad in (
        None,
        Quote("AAPL", None, None, None, QuoteKind.OFFICIAL_CLOSE),
        Quote("AAPL", Decimal("12"), session.close - timedelta(days=3), "test", QuoteKind.OFFICIAL_CLOSE),
        Quote("AAPL", Decimal("12"), session.close, "test", QuoteKind.LAST),
    ):
        m = mark_close(bad, symbol="AAPL", session=session)
        assert m.status is MarkStatus.UNMARKED and m.price is None and m.issues


def test_book_trust_requires_every_holding_to_be_marked(calendar):
    session = calendar.session(date(2026, 7, 6))
    good = mark_close(
        Quote("AAPL", Decimal("12"), session.close, "t", QuoteKind.OFFICIAL_CLOSE), symbol="AAPL", session=session
    )
    bad = mark_close(None, symbol="SEM", session=session)
    assert book_trust([good]).trusted
    t = book_trust([good, bad])
    assert not t.trusted and t.unmarked == ("SEM",)
    assert book_trust([]).trusted
