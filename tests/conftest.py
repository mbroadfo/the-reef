from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from tests.fixtures.market import load_calendar, standard_actions, standard_master
from the_reef.execution.gate import GatePorts
from the_reef.risk.limits import RiskLimits

NY = ZoneInfo("America/New_York")


def ny(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    """A timezone-aware New York wall-clock time."""
    return datetime(year, month, day, hour, minute, second, tzinfo=NY)


@pytest.fixture(scope="session")
def calendar():
    return load_calendar()


@pytest.fixture()
def ports(calendar):
    return GatePorts(calendar, standard_master(), standard_actions(), RiskLimits())


@pytest.fixture()
def limits():
    return RiskLimits()


@pytest.fixture()
def utc():
    return timezone.utc
