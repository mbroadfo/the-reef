"""Daily bars with point-in-time access (no look-ahead).

A day's bar is complete only when its session has closed, so it becomes knowable at that
session's close. ``BarSource.history`` therefore takes ``as_of`` and never returns a bar whose
session had not closed by then. The official open of a session is knowable at the open and is
served as a ``Quote`` (``official_open``); the official close likewise at the close.

``StaticBarSource`` serves fixtures and cached data. A production adapter must keep the same
contract and refuse a query it cannot answer point-in-time (see docs/reef2-ledger.md, later
slice requirement 2).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Mapping, Protocol, Sequence

from the_reef.market.calendar import MarketCalendar, Session
from the_reef.market.quotes import Quote, QuoteKind


@dataclass(frozen=True)
class DailyBar:
    symbol: str
    day: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    source: str

    def __post_init__(self) -> None:
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError(f"{self.symbol} {self.day}: prices must be positive")
        if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close, self.high):
            raise ValueError(f"{self.symbol} {self.day}: inconsistent OHLC")
        if self.volume < 0:
            raise ValueError("negative volume")


class BarSource(Protocol):
    def history(self, symbol: str, as_of: datetime, limit: int | None = None) -> Sequence[DailyBar]:
        """Bars of sessions that had closed by ``as_of``, oldest first, the last ``limit`` of them."""
        ...

    def bar(self, symbol: str, day: date, as_of: datetime) -> DailyBar | None:
        """The bar of ``day`` if that session had closed by ``as_of``, else None."""
        ...

    def official_open(self, symbol: str, session: Session) -> Quote | None: ...

    def official_close(self, symbol: str, session: Session) -> Quote | None: ...


class StaticBarSource:
    def __init__(self, bars: Sequence[DailyBar], calendar: MarketCalendar) -> None:
        self._cal = calendar
        self._by_symbol: dict[str, dict[date, DailyBar]] = {}
        for b in bars:
            if calendar.session(b.day) is None:
                raise ValueError(f"{b.symbol}: bar on {b.day}, which is not a session")
            self._by_symbol.setdefault(b.symbol, {})[b.day] = b

    def symbols(self) -> list[str]:
        return sorted(self._by_symbol)

    def _closed(self, day: date, as_of: datetime) -> bool:
        s = self._cal.session(day)
        return s is not None and s.close <= as_of

    def history(self, symbol: str, as_of: datetime, limit: int | None = None) -> Sequence[DailyBar]:
        days = self._by_symbol.get(symbol, {})
        out = [days[d] for d in sorted(days) if self._closed(d, as_of)]
        return tuple(out[-limit:] if limit else out)

    def bar(self, symbol: str, day: date, as_of: datetime) -> DailyBar | None:
        b = self._by_symbol.get(symbol, {}).get(day)
        return b if b is not None and self._closed(day, as_of) else None

    def official_open(self, symbol: str, session: Session) -> Quote | None:
        b = self._by_symbol.get(symbol, {}).get(session.day)
        return None if b is None else Quote(symbol, b.open, session.open, b.source, QuoteKind.OFFICIAL_OPEN)

    def official_close(self, symbol: str, session: Session) -> Quote | None:
        b = self._by_symbol.get(symbol, {}).get(session.day)
        return None if b is None else Quote(symbol, b.close, session.close, b.source, QuoteKind.OFFICIAL_CLOSE)


def last_closes(source: BarSource, symbols: Sequence[str], as_of: datetime) -> Mapping[str, Decimal | None]:
    """Latest close known at ``as_of`` per symbol (None when there is none)."""
    out: dict[str, Decimal | None] = {}
    for s in symbols:
        h = source.history(s, as_of, 1)
        out[s] = h[-1].close if h else None
    return out
