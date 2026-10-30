from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tests.fixtures.market import SEM_EVIDENCE, standard_actions, standard_master
from the_reef.market.instruments import (
    Intent,
    InvalidSymbol,
    TradabilityCode,
    check_tradable,
    normalize_symbol,
    settlements_due,
)


@pytest.mark.parametrize("raw, expected", [("aapl", "AAPL"), (" SEM ", "SEM"), ("brk.b", "BRK.B"), ("BF-B", "BF-B")])
def test_normalize_symbol_accepts(raw, expected):
    assert normalize_symbol(raw) == expected


@pytest.mark.parametrize("raw", ["", "  ", "$AAPL", "AAPL1", "TOOLONGSYM", "A B", "AA.PL.X", "AAPL;DROP", "BRK..B", None, 123])
def test_normalize_symbol_rejects(raw):
    with pytest.raises(InvalidSymbol):
        normalize_symbol(raw)  # type: ignore[arg-type]


def check(calendar, symbol, day, intent=Intent.OPEN, min_history=60):
    return check_tradable(
        symbol, day, standard_master(), standard_actions(), calendar, intent=intent, min_history_sessions=min_history
    )


def test_active_seasoned_name_is_tradable(calendar):
    r = check(calendar, "AAPL", date(2026, 7, 2))
    assert r.ok and r.code is TradabilityCode.OK


def test_invalid_and_unknown_symbols(calendar):
    assert check(calendar, "12!", date(2026, 7, 2)).code is TradabilityCode.INVALID_SYMBOL
    assert check(calendar, "ZZZZ", date(2026, 7, 2)).code is TradabilityCode.UNKNOWN_SYMBOL


def test_halted_blocks_every_intent(calendar):
    for intent in Intent:
        assert check(calendar, "HALT", date(2026, 7, 2), intent).code is TradabilityCode.HALTED


def test_delisted_blocks_every_intent_including_selling(calendar):
    for intent in Intent:
        r = check(calendar, "GONE", date(2026, 7, 2), intent)
        assert not r.ok and r.code is TradabilityCode.DELISTED


def test_acquired_name_after_last_trading_day_is_not_tradable(calendar):
    for intent in Intent:
        r = check(calendar, "SEM", date(2026, 7, 2), intent)
        assert not r.ok and r.code is TradabilityCode.ACQUIRED
        assert r.evidence == SEM_EVIDENCE


def test_acquired_name_is_closable_on_its_last_trading_day_but_not_openable(calendar):
    assert check(calendar, "SEM", date(2026, 6, 30), Intent.CLOSE).ok
    r = check(calendar, "SEM", date(2026, 6, 30), Intent.OPEN)
    assert not r.ok and r.code is TradabilityCode.PENDING_CASH_DEAL and r.evidence == SEM_EVIDENCE


def test_not_yet_listed(calendar):
    assert check(calendar, "SPCX", date(2026, 6, 11)).code is TradabilityCode.NOT_YET_LISTED


def test_fresh_listing_needs_minimum_history_to_open_or_add_only(calendar):
    day = date(2026, 7, 1)  # 13 sessions since the first trade date
    assert check(calendar, "SPCX", day, Intent.OPEN).code is TradabilityCode.INSUFFICIENT_HISTORY
    assert check(calendar, "SPCX", day, Intent.ADD).code is TradabilityCode.INSUFFICIENT_HISTORY
    assert check(calendar, "SPCX", day, Intent.CLOSE).ok
    assert check(calendar, "SPCX", day, Intent.REDUCE).ok
    assert check(calendar, "SPCX", day, Intent.OPEN, min_history=10).ok


def test_settlement_cash_out_uses_the_filed_price_not_a_quote():
    due = settlements_due({"SEM": 100, "AAPL": 5, "FLAT": 0}, standard_actions(), date(2026, 7, 1))
    assert len(due) == 1
    assert (due[0].symbol, due[0].cash, due[0].effective) == ("SEM", Decimal("1650.00"), date(2026, 7, 1))
    assert due[0].evidence == SEM_EVIDENCE


def test_no_settlement_before_the_effective_date():
    assert settlements_due({"SEM": 100}, standard_actions(), date(2026, 6, 30)) == []
