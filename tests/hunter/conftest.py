from __future__ import annotations

from datetime import timedelta

import pytest

from tests.fixtures.hunter_scenario import START_INDEX, make_deps, make_world
from the_reef.engine.advance import advance, bootstrap
from the_reef.ledger.ledger import Ledger


@pytest.fixture(scope="session")
def world():
    return make_world()


@pytest.fixture()
def deps(world):
    return make_deps(world)


def start(world, deps, ledger=None):
    led = ledger or Ledger()
    bootstrap(led, deps, world.calendar.session(world.days[START_INDEX]).open - timedelta(hours=1))
    return led


def run(world, deps, ledger, first, last):
    """Advance sessions first..last (inclusive indexes into world.days); returns the reports."""
    return [advance(ledger, deps, world.days[i]) for i in range(first, last + 1)]


@pytest.fixture(scope="session")
def full_run(world):
    """The complete 65-session simulation, shared by the read-only assertions."""
    deps = make_deps(world)
    led = start(world, deps)
    reports = run(world, deps, led, START_INDEX, START_INDEX + 64)
    return deps, led, reports
