"""Quote validity, marking and book trust (requirement I-4; defects E-5, E-6).

1.0 returned a bare ``last_price`` (or None on any failure) with no timestamp and no source, and
callers silently kept the previous price. Here a price is only usable if it carries a source, a
timestamp inside the session, and passes a freshness test; otherwise the position is UNMARKED and
the book is UNTRUSTED. Pure functions; no clock is read.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Mapping, Protocol, Sequence

from the_reef.market.calendar import Session


class QuoteKind(str, Enum):
    LAST = "LAST"
    OFFICIAL_OPEN = "OFFICIAL_OPEN"
    OFFICIAL_CLOSE = "OFFICIAL_CLOSE"


class QuoteIssue(str, Enum):
    MISSING = "MISSING"
    WRONG_SYMBOL = "WRONG_SYMBOL"
    NON_POSITIVE_PRICE = "NON_POSITIVE_PRICE"
    NO_TIMESTAMP = "NO_TIMESTAMP"
    NO_SOURCE = "NO_SOURCE"
    FUTURE_TIMESTAMP = "FUTURE_TIMESTAMP"
    STALE = "STALE"
    OUTSIDE_SESSION = "OUTSIDE_SESSION"
    WRONG_KIND = "WRONG_KIND"


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: Decimal | None
    as_of: datetime | None
    source: str | None
    kind: QuoteKind = QuoteKind.LAST


@dataclass(frozen=True)
class QuoteCheck:
    valid: bool
    issues: tuple[QuoteIssue, ...] = ()

    @property
    def usable_price(self) -> bool:
        return self.valid


class QuoteSource(Protocol):
    def get_quote(self, symbol: str, kind: QuoteKind, session: Session) -> Quote | None: ...


DEFAULT_MAX_AGE = timedelta(minutes=20)
DEFAULT_PRINT_TOLERANCE = timedelta(minutes=5)


def validate_quote(
    quote: Quote | None,
    *,
    symbol: str,
    now: datetime,
    max_age: timedelta = DEFAULT_MAX_AGE,
    required_kind: QuoteKind | None = None,
) -> QuoteCheck:
    """General validity: present, right symbol, positive, stamped, sourced, not future, not stale."""
    if quote is None:
        return QuoteCheck(False, (QuoteIssue.MISSING,))
    issues: list[QuoteIssue] = []
    if quote.symbol != symbol:
        issues.append(QuoteIssue.WRONG_SYMBOL)
    if quote.price is None or quote.price <= 0:
        issues.append(QuoteIssue.NON_POSITIVE_PRICE)
    if not quote.source:
        issues.append(QuoteIssue.NO_SOURCE)
    if quote.as_of is None:
        issues.append(QuoteIssue.NO_TIMESTAMP)
    else:
        if quote.as_of.tzinfo is None:
            issues.append(QuoteIssue.NO_TIMESTAMP)
        elif quote.as_of > now:
            issues.append(QuoteIssue.FUTURE_TIMESTAMP)
        elif now - quote.as_of > max_age:
            issues.append(QuoteIssue.STALE)
    if required_kind is not None and quote.kind is not required_kind:
        issues.append(QuoteIssue.WRONG_KIND)
    return QuoteCheck(not issues, tuple(issues))


def validate_fill_quote(
    quote: Quote | None,
    *,
    symbol: str,
    session: Session,
    tolerance: timedelta = DEFAULT_PRINT_TOLERANCE,
) -> QuoteCheck:
    """A fill needs the official open print of that session, stamped within ``tolerance`` of the open.

    Retrieval may happen later than the print, so freshness is judged on the print's own timestamp
    against the session, not against the wall clock.
    """
    if quote is None:
        return QuoteCheck(False, (QuoteIssue.MISSING,))
    issues: list[QuoteIssue] = []
    if quote.symbol != symbol:
        issues.append(QuoteIssue.WRONG_SYMBOL)
    if quote.price is None or quote.price <= 0:
        issues.append(QuoteIssue.NON_POSITIVE_PRICE)
    if not quote.source:
        issues.append(QuoteIssue.NO_SOURCE)
    if quote.kind is not QuoteKind.OFFICIAL_OPEN:
        issues.append(QuoteIssue.WRONG_KIND)
    if quote.as_of is None or quote.as_of.tzinfo is None:
        issues.append(QuoteIssue.NO_TIMESTAMP)
    elif not (session.open <= quote.as_of <= session.open + tolerance):
        issues.append(QuoteIssue.OUTSIDE_SESSION)
    return QuoteCheck(not issues, tuple(issues))


class MarkStatus(str, Enum):
    MARKED = "MARKED"
    UNMARKED = "UNMARKED"


@dataclass(frozen=True)
class MarkResult:
    symbol: str
    status: MarkStatus
    price: Decimal | None = None
    issues: tuple[QuoteIssue, ...] = ()


def mark_close(
    quote: Quote | None,
    *,
    symbol: str,
    session: Session,
    tolerance: timedelta = DEFAULT_PRINT_TOLERANCE,
) -> MarkResult:
    """Value a held name at the session close. A missing or invalid close is UNMARKED.

    There is deliberately no ``previous_price`` argument: a failed mark is never papered over
    with the last known value (defect E-6).
    """
    if quote is None:
        return MarkResult(symbol, MarkStatus.UNMARKED, None, (QuoteIssue.MISSING,))
    issues: list[QuoteIssue] = []
    if quote.symbol != symbol:
        issues.append(QuoteIssue.WRONG_SYMBOL)
    if quote.price is None or quote.price <= 0:
        issues.append(QuoteIssue.NON_POSITIVE_PRICE)
    if not quote.source:
        issues.append(QuoteIssue.NO_SOURCE)
    if quote.kind is not QuoteKind.OFFICIAL_CLOSE:
        issues.append(QuoteIssue.WRONG_KIND)
    if quote.as_of is None or quote.as_of.tzinfo is None:
        issues.append(QuoteIssue.NO_TIMESTAMP)
    elif not (session.close - tolerance <= quote.as_of <= session.close + tolerance):
        issues.append(QuoteIssue.OUTSIDE_SESSION)
    if issues:
        return MarkResult(symbol, MarkStatus.UNMARKED, None, tuple(issues))
    return MarkResult(symbol, MarkStatus.MARKED, quote.price)


@dataclass(frozen=True)
class BookTrust:
    trusted: bool
    unmarked: tuple[str, ...] = field(default_factory=tuple)


def book_trust(marks: Sequence[MarkResult]) -> BookTrust:
    """The book is UNTRUSTED if any held name is UNMARKED; new exposure is then blocked (D8e)."""
    unmarked = tuple(sorted(m.symbol for m in marks if m.status is MarkStatus.UNMARKED))
    return BookTrust(not unmarked, unmarked)


def marks_by_symbol(marks: Sequence[MarkResult]) -> Mapping[str, MarkResult]:
    return {m.symbol: m for m in marks}
