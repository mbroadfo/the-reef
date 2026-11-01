from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from the_reef.market.calendar import (
    CalendarRangeError,
    ExchangeCalendar,
    TimePhase,
    can_fill_immediately,
    classify,
    next_valid_open,
)
from tests.conftest import ny
from tests.fixtures.market import load_calendar

# NYSE 2026 H2 closures and early closes: [V] from exchange_calendars 4.13.2, consistent with the
# NYSE published holiday schedule [R]. Independence Day falls on Saturday, so Friday 07-03 is closed.
CLOSED_WEEKDAYS = [date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25)]
EARLY_CLOSES = [date(2026, 11, 27), date(2026, 12, 24)]


def test_cached_fixture_matches_the_library():
    """If exchange_calendars ever disagrees with the cached data, this fails and a human looks."""
    lib = ExchangeCalendar()
    static = load_calendar()
    day = static.first_day
    while day <= static.last_day:
        a, b = lib.session(day), static.session(day)
        assert (a is None) == (b is None), day
        if a is not None and b is not None:
            assert (a.open, a.close) == (b.open, b.close), day
        day = date.fromordinal(day.toordinal() + 1)


@pytest.mark.parametrize("day", CLOSED_WEEKDAYS)
def test_known_holidays_are_not_sessions(calendar, day):
    assert calendar.session(day) is None


@pytest.mark.parametrize("day", EARLY_CLOSES)
def test_early_closes_close_at_1pm_new_york(calendar, day):
    s = calendar.session(day)
    assert s is not None and s.early_close
    assert s.close.astimezone(ny(2026, 1, 1).tzinfo).hour == 13


def test_open_follows_daylight_saving(calendar):
    assert calendar.session(date(2026, 10, 30)).open == datetime(2026, 10, 30, 13, 30, tzinfo=timezone.utc)  # EDT
    assert calendar.session(date(2026, 11, 2)).open == datetime(2026, 11, 2, 14, 30, tzinfo=timezone.utc)  # EST


@pytest.mark.parametrize(
    "when, phase",
    [
        (ny(2026, 7, 2, 9, 29, 59), TimePhase.PRE_MARKET),
        (ny(2026, 7, 2, 9, 30), TimePhase.REGULAR),
        (ny(2026, 7, 2, 15, 59, 59), TimePhase.REGULAR),
        (ny(2026, 7, 2, 16, 0), TimePhase.AFTER_CLOSE),
        (ny(2026, 7, 3, 9, 35), TimePhase.HOLIDAY),
        (ny(2026, 7, 4, 11, 0), TimePhase.WEEKEND),
        (ny(2026, 7, 5, 11, 0), TimePhase.WEEKEND),
        (ny(2026, 11, 26, 11, 0), TimePhase.HOLIDAY),
        (ny(2026, 11, 27, 12, 59), TimePhase.REGULAR),
        (ny(2026, 11, 27, 13, 0), TimePhase.AFTER_CLOSE),
        (ny(2026, 11, 27, 14, 0), TimePhase.AFTER_CLOSE),
    ],
)
def test_classify(calendar, when, phase):
    assert classify(calendar, when).phase is phase


def test_classification_uses_new_york_date_not_utc_date(calendar):
    # 20:07 ET on 2026-06-30 is already 2026-07-01 in UTC; it is still the 06-30 session.
    c = classify(calendar, datetime(2026, 7, 1, 0, 7, 15, tzinfo=timezone.utc))
    assert c.local_day == date(2026, 6, 30) and c.phase is TimePhase.AFTER_CLOSE


def test_naive_timestamps_are_rejected(calendar):
    with pytest.raises(ValueError):
        classify(calendar, datetime(2026, 7, 2, 10, 0))
    with pytest.raises(ValueError):
        next_valid_open(calendar, datetime(2026, 7, 2, 10, 0))


@pytest.mark.parametrize(
    "decided, fills",
    [
        (ny(2026, 7, 2, 8, 0), date(2026, 7, 2)),  # pre-market: same day's open
        (ny(2026, 7, 2, 9, 30), date(2026, 7, 6)),  # at the open: the next open (07-03 is a holiday)
        (ny(2026, 7, 2, 16, 0), date(2026, 7, 6)),  # after close before a holiday weekend
        (ny(2026, 6, 30, 20, 7, 15), date(2026, 7, 1)),
        (ny(2026, 7, 4, 12, 0), date(2026, 7, 6)),  # Saturday
        (ny(2026, 11, 25, 17, 0), date(2026, 11, 27)),  # day before Thanksgiving
    ],
)
def test_next_valid_open(calendar, decided, fills):
    s = next_valid_open(calendar, decided)
    assert s.day == fills
    assert s.open > decided


def test_can_fill_immediately_only_in_regular_hours(calendar):
    assert can_fill_immediately(calendar, ny(2026, 7, 2, 10, 0))
    for t in (ny(2026, 7, 2, 8, 0), ny(2026, 7, 2, 16, 30), ny(2026, 7, 3, 10, 0), ny(2026, 7, 4, 10, 0)):
        assert not can_fill_immediately(calendar, t)


def test_out_of_range_fails_closed(calendar):
    with pytest.raises(CalendarRangeError):
        calendar.session(date(2027, 1, 4))
    with pytest.raises(CalendarRangeError):
        classify(calendar, ny(2027, 1, 5, 10, 0))
    with pytest.raises(CalendarRangeError):
        next_valid_open(calendar, ny(2026, 12, 31, 17, 0))  # no known session after the fixture's end


def test_exchange_calendar_range_edge_fails_closed():
    lib = ExchangeCalendar()
    with pytest.raises(CalendarRangeError):
        lib.session(date(lib.last_day.year + 2, 1, 4))
    with pytest.raises(CalendarRangeError):
        lib.next_session(lib.last_day)


def test_session_count(calendar):
    assert calendar.session_count(date(2026, 7, 1), date(2026, 7, 6)) == 3  # 07-01, 07-02, 07-06; 07-03 is closed


def test_history_for_a_listing_older_than_the_calendar_counts_weekdays_before_coverage(calendar):
    from the_reef.market.calendar import session_age_days

    assert session_age_days(calendar, date(1980, 12, 12), date(2026, 7, 2)) > 10000
    assert session_age_days(calendar, date(2026, 6, 12), date(2026, 7, 1)) == 13  # 06-19 (Juneteenth) is closed
    assert session_age_days(calendar, date(2026, 7, 2), date(2026, 7, 1)) == 0
