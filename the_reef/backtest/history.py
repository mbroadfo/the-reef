"""Point-in-time bar source over cached historical data, plus a data-quality audit.

Behaves like ``StaticBarSource`` (a bar is visible only once its session has closed) but indexes
sessions once, so replaying ~100 symbols over years stays fast. Rows that are not valid sessions
or have inconsistent OHLC are dropped and counted, never repaired.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Sequence

from the_reef.backtest import cache
from the_reef.market.bars import DailyBar
from the_reef.market.calendar import MarketCalendar, Session
from the_reef.market.quotes import Quote, QuoteKind

SOURCE = "yahoo-cache"
_PX = Decimal("0.0001")


def _px(x: Decimal) -> Decimal:
    """Yahoo prices carry float noise; keep four decimals, enough for split-adjusted history."""
    return x.quantize(_PX)


class CachedCalendar:
    """Memoises a calendar; session lookups against exchange_calendars are the replay's hot path."""

    def __init__(self, inner: MarketCalendar) -> None:
        self._inner = inner
        self._sessions: dict[date, Session | None] = {}
        self.first_day, self.last_day = inner.first_day, inner.last_day

    def session(self, day: date) -> Session | None:
        if day not in self._sessions:
            self._sessions[day] = self._inner.session(day)
        return self._sessions[day]

    def next_session(self, day: date) -> Session:
        return self._inner.next_session(day)

    def session_count(self, start: date, end: date) -> int:
        return self._inner.session_count(start, end)


@dataclass
class SymbolQuality:
    symbol: str
    rows: int = 0
    first: date | None = None
    last: date | None = None
    dropped_not_session: int = 0
    dropped_bad_ohlc: int = 0
    duplicate_dates: int = 0  # extra rows for a date already seen; the first is kept
    conflicting_duplicates: int = 0  # ...and the repeat disagreed with it
    missing_sessions: int = 0  # sessions between first and last with no row
    splits: int = 0
    dividends: int = 0
    max_gap_sessions: int = 0


@dataclass
class QualityReport:
    per_symbol: dict[str, SymbolQuality] = field(default_factory=dict)

    def total(self, attr: str) -> int:
        return sum(getattr(q, attr) for q in self.per_symbol.values())


class HistoricalBarSource:
    def __init__(self, calendar: MarketCalendar, symbols: Sequence[str], root=None) -> None:
        self._cal = calendar
        self.quality = QualityReport()
        self._days: dict[str, list[date]] = {}
        self._bars: dict[str, dict[date, DailyBar]] = {}
        all_days: set[date] = set()
        for sym in symbols:
            q = SymbolQuality(sym)
            bars: dict[date, DailyBar] = {}
            seen: dict[date, cache.RawRow] = {}
            for r in cache.read(sym, root):
                q.rows += 1
                if r.day in seen:
                    q.duplicate_dates += 1
                    f = seen[r.day]
                    if (f.open, f.high, f.low, f.close, f.volume) != (r.open, r.high, r.low, r.close, r.volume):
                        q.conflicting_duplicates += 1
                    continue
                seen[r.day] = r
                if r.split not in (0, 1):
                    q.splits += 1
                if r.dividend > 0:
                    q.dividends += 1
                try:
                    if not (calendar.first_day <= r.day <= calendar.last_day) or calendar.session(r.day) is None:
                        q.dropped_not_session += 1
                        continue
                    bars[r.day] = DailyBar(sym, r.day, _px(r.open), _px(r.high), _px(r.low), _px(r.close), r.volume, SOURCE)
                except ValueError:
                    q.dropped_bad_ohlc += 1
            self._bars[sym] = bars
            self._days[sym] = sorted(bars)
            if bars:
                q.first, q.last = self._days[sym][0], self._days[sym][-1]
            self.quality.per_symbol[sym] = q
            all_days |= set(bars)
        # Every session any symbol traded; used to find a symbol's missing observations.
        self._universe_days = sorted(all_days)
        for sym, q in self.quality.per_symbol.items():
            if q.first is None:
                continue
            have = set(self._bars[sym])
            expected = [d for d in self._universe_days if q.first <= d <= q.last]
            missing = [d for d in expected if d not in have]
            q.missing_sessions = len(missing)
            run = best = 0
            for d in expected:
                run = 0 if d in have else run + 1
                best = max(best, run)
            q.max_gap_sessions = best
        # Session closes in order, for bisecting "which sessions had closed by as_of".
        self._closes = [(d, calendar.session(d).close) for d in self._universe_days]  # type: ignore[union-attr]
        self._close_times = [c for _, c in self._closes]

    def symbols(self) -> list[str]:
        return sorted(self._bars)

    def days(self, symbol: str) -> list[date]:
        """Every session this symbol has a bar for, oldest first."""
        return list(self._days.get(symbol, ()))

    def _last_closed_day_index(self, as_of: datetime) -> int:
        return bisect_right(self._close_times, as_of)

    def history(self, symbol: str, as_of: datetime, limit: int | None = None) -> Sequence[DailyBar]:
        days = self._days.get(symbol, [])
        if not days:
            return ()
        n = self._last_closed_day_index(as_of)
        cutoff = self._closes[n - 1][0] if n else None
        if cutoff is None:
            return ()
        hi = bisect_right(days, cutoff)
        lo = max(0, hi - limit) if limit else 0
        bars = self._bars[symbol]
        return tuple(bars[d] for d in days[lo:hi])

    def bar(self, symbol: str, day: date, as_of: datetime) -> DailyBar | None:
        s = self._cal.session(day)
        b = self._bars.get(symbol, {}).get(day)
        return b if b is not None and s is not None and s.close <= as_of else None

    def official_open(self, symbol: str, session: Session) -> Quote | None:
        b = self._bars.get(symbol, {}).get(session.day)
        return None if b is None else Quote(symbol, b.open, session.open, b.source, QuoteKind.OFFICIAL_OPEN)

    def official_close(self, symbol: str, session: Session) -> Quote | None:
        b = self._bars.get(symbol, {}).get(session.day)
        return None if b is None else Quote(symbol, b.close, session.close, b.source, QuoteKind.OFFICIAL_CLOSE)
