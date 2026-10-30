"""Market calendar: sessions, order-time classification and next-valid-open logic.

Pure functions over a ``MarketCalendar``. Nothing here reads a clock, the network or a
database; every timestamp is passed in and must be timezone-aware.

Fail closed: a date outside the calendar's known range raises ``CalendarRangeError``
instead of guessing that the market is open.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")


class CalendarRangeError(ValueError):
    """The requested date is outside the range the calendar can answer for."""


class TimePhase(str, Enum):
    REGULAR = "REGULAR"
    PRE_MARKET = "PRE_MARKET"
    AFTER_CLOSE = "AFTER_CLOSE"
    WEEKEND = "WEEKEND"
    HOLIDAY = "HOLIDAY"


@dataclass(frozen=True)
class Session:
    day: date
    open: datetime  # timezone-aware, UTC
    close: datetime  # timezone-aware, UTC
    early_close: bool = False

    def __post_init__(self) -> None:
        if self.open.tzinfo is None or self.close.tzinfo is None:
            raise ValueError("Session open/close must be timezone-aware")
        if self.close <= self.open:
            raise ValueError("Session close must be after open")


@dataclass(frozen=True)
class TimeClassification:
    phase: TimePhase
    session: Session | None  # the session of that calendar day, None when closed all day
    local_day: date


@runtime_checkable
class MarketCalendar(Protocol):
    first_day: date
    last_day: date

    def session(self, day: date) -> Session | None:
        """The session on ``day``, or None if the exchange is closed all day.

        Raises ``CalendarRangeError`` outside ``[first_day, last_day]``.
        """
        ...

    def next_session(self, day: date) -> Session:
        """The first session strictly after ``day``. Raises ``CalendarRangeError`` at the edge."""
        ...

    def session_count(self, start: date, end: date) -> int:
        """Number of sessions in ``[start, end]`` inclusive."""
        ...


class StaticCalendar:
    """Calendar built from an explicit list of sessions (fixtures, cached data)."""

    def __init__(self, sessions: list[Session], first_day: date, last_day: date) -> None:
        self._by_day = {s.day: s for s in sessions}
        self._days = sorted(self._by_day)
        self.first_day = first_day
        self.last_day = last_day

    def _check(self, day: date) -> None:
        if not (self.first_day <= day <= self.last_day):
            raise CalendarRangeError(f"{day} outside calendar range {self.first_day}..{self.last_day}")

    def session(self, day: date) -> Session | None:
        self._check(day)
        return self._by_day.get(day)

    def next_session(self, day: date) -> Session:
        self._check(day)
        for d in self._days:
            if d > day:
                return self._by_day[d]
        raise CalendarRangeError(f"no session after {day} within calendar range ending {self.last_day}")

    def session_count(self, start: date, end: date) -> int:
        self._check(start)
        self._check(end)
        return sum(1 for d in self._days if start <= d <= end)


class ExchangeCalendar:
    """NYSE calendar backed by the ``exchange_calendars`` package (decision D7).

    Imported lazily so modules that only need the interface do not pull in pandas.
    """

    def __init__(self, name: str = "XNYS") -> None:
        import exchange_calendars as xc  # noqa: PLC0415

        self._xc = xc
        self._cal = xc.get_calendar(name)
        self.first_day = self._cal.first_session.date()
        self.last_day = self._cal.last_session.date()

    def _ts(self, day: date):
        import pandas as pd  # noqa: PLC0415

        if not (self.first_day <= day <= self.last_day):
            raise CalendarRangeError(f"{day} outside calendar range {self.first_day}..{self.last_day}")
        return pd.Timestamp(day)

    def session(self, day: date) -> Session | None:
        ts = self._ts(day)
        if not self._cal.is_session(ts):
            return None
        open_ = self._cal.session_open(ts).to_pydatetime().astimezone(timezone.utc)
        close = self._cal.session_close(ts).to_pydatetime().astimezone(timezone.utc)
        local_close = close.astimezone(NEW_YORK).time()
        early = local_close.hour < 16
        return Session(day=day, open=open_, close=close, early_close=early)

    def next_session(self, day: date) -> Session:
        ts = self._ts(day)
        try:
            nxt = self._cal.next_session(ts)
        except Exception as exc:  # exchange_calendars raises its own DateOutOfBounds
            raise CalendarRangeError(f"no session after {day}: {exc}") from exc
        session = self.session(nxt.date())
        assert session is not None
        return session

    def session_count(self, start: date, end: date) -> int:
        self._ts(start)
        self._ts(end)
        return len(self._cal.sessions_in_range(start.isoformat(), end.isoformat()))


def _require_aware(ts: datetime) -> datetime:
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        raise ValueError("timestamp must be timezone-aware")
    return ts


def classify(calendar: MarketCalendar, ts: datetime) -> TimeClassification:
    """Classify an instant relative to the exchange day (New York local date)."""
    ts = _require_aware(ts)
    local_day = ts.astimezone(NEW_YORK).date()
    session = calendar.session(local_day)
    if session is None:
        phase = TimePhase.WEEKEND if local_day.weekday() >= 5 else TimePhase.HOLIDAY
        return TimeClassification(phase, None, local_day)
    if ts < session.open:
        return TimeClassification(TimePhase.PRE_MARKET, session, local_day)
    if ts >= session.close:
        return TimeClassification(TimePhase.AFTER_CLOSE, session, local_day)
    return TimeClassification(TimePhase.REGULAR, session, local_day)


def next_valid_open(calendar: MarketCalendar, ts: datetime) -> Session:
    """The first session whose open is strictly after ``ts`` (decide at close, fill at next open)."""
    ts = _require_aware(ts)
    local_day = ts.astimezone(NEW_YORK).date()
    same_day = calendar.session(local_day)
    if same_day is not None and ts < same_day.open:
        return same_day
    return calendar.next_session(local_day)


def can_fill_immediately(calendar: MarketCalendar, ts: datetime) -> bool:
    """True only inside a regular session. 1.0 filled outside it (defects E-1, E-2)."""
    return classify(calendar, ts).phase is TimePhase.REGULAR


def session_age_days(calendar: MarketCalendar, start: date, end: date) -> int:
    """Sessions between ``start`` and ``end`` inclusive, for minimum-history rules.

    When ``start`` predates the calendar's coverage the part before ``first_day`` is counted as
    weekdays (an upper bound that ignores holidays). That only happens for listings that are
    decades old relative to any history rule, so the approximation cannot admit a young listing.
    """
    if end < start:
        return 0
    if start >= calendar.first_day:
        return calendar.session_count(start, end)
    before = 0
    day = start
    while day < calendar.first_day:
        if day.weekday() < 5:
            before += 1
        day = date.fromordinal(day.toordinal() + 1)
    return before + calendar.session_count(calendar.first_day, end)


__all__ = [
    "CalendarRangeError",
    "ExchangeCalendar",
    "MarketCalendar",
    "NEW_YORK",
    "Session",
    "StaticCalendar",
    "TimeClassification",
    "TimePhase",
    "can_fill_immediately",
    "classify",
    "next_valid_open",
    "session_age_days",
]
