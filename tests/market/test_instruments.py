from __future__ import annotations

from datetime import date, datetime, timezone
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


NOW = datetime(2026, 7, 2, 14, 0, tzinfo=timezone.utc)


def check(calendar, symbol, day, intent=Intent.OPEN, min_history=60):
    return check_tradable(
        symbol, day, standard_master(), standard_actions(), calendar, intent=intent, as_of=NOW, min_history_sessions=min_history
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
    due = settlements_due({"SEM": 100, "AAPL": 5, "FLAT": 0}, standard_actions(), date(2026, 7, 1), holder="sleeve-a", as_of=NOW)
    assert len(due) == 1
    assert (due[0].symbol, due[0].cash, due[0].effective) == ("SEM", Decimal("1650.00"), date(2026, 7, 1))
    assert due[0].evidence == SEM_EVIDENCE


def test_no_settlement_before_the_effective_date():
    assert settlements_due({"SEM": 100}, standard_actions(), date(2026, 6, 30), holder="sleeve-a", as_of=NOW) == []


# --- point-in-time lookups: a backtest must not see later knowledge ---------------------------

from dataclasses import replace  # noqa: E402

from tests.fixtures.market import SEM_DEAL  # noqa: E402
from the_reef.market.instruments import (  # noqa: E402
    CorporateAction,
    StaticCorporateActions,
    StaticInstrumentMaster,
)

UTC = timezone.utc


def test_master_returns_the_vintage_known_at_the_query_time():
    master = standard_master()
    assert master.get("SEM", datetime(2026, 6, 22, tzinfo=UTC)).status.value == "ACTIVE"
    assert master.get("SEM", datetime(2026, 7, 2, tzinfo=UTC)).status.value == "ACQUIRED"
    assert master.get("SEM", datetime(2019, 1, 1, tzinfo=UTC)) is None  # not yet in the master


def test_backtest_before_the_delisting_does_not_see_the_delisting(calendar):
    r = check_tradable(
        "SEM", date(2026, 6, 22), standard_master(), StaticCorporateActions([]), calendar,
        intent=Intent.OPEN, as_of=datetime(2026, 6, 19, 21, 0, tzinfo=UTC),
    )
    assert r.ok  # honest: nothing about the deal was public yet in this scenario


def test_actions_are_invisible_before_they_are_known(calendar):
    late = replace(SEM_DEAL, known_at=datetime(2026, 6, 30, tzinfo=UTC))
    actions = StaticCorporateActions([late])
    before = datetime(2026, 6, 19, 21, 0, tzinfo=UTC)
    assert actions.actions_for("SEM", before) == ()
    assert len(actions.actions_for("SEM", datetime(2026, 6, 30, tzinfo=UTC))) == 1
    assert check_tradable("SEM", date(2026, 6, 22), standard_master(), actions, calendar, intent=Intent.OPEN, as_of=before).ok
    after = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    blocked = check_tradable("SEM", date(2026, 7, 2), standard_master(), actions, calendar, intent=Intent.OPEN, as_of=after)
    assert blocked.code is TradabilityCode.ACQUIRED


def test_a_later_restatement_replaces_the_earlier_one_only_once_known():
    restated = replace(SEM_DEAL, known_at=datetime(2026, 3, 1, tzinfo=UTC), cash_per_share=Decimal("17.00"))
    actions = StaticCorporateActions([SEM_DEAL, restated])
    [early] = actions.actions_for("SEM", datetime(2026, 1, 1, tzinfo=UTC))
    [late] = actions.actions_for("SEM", datetime(2026, 4, 1, tzinfo=UTC))
    assert early.cash_per_share == Decimal("16.50") and late.cash_per_share == Decimal("17.00")
    assert early.action_id == late.action_id


def test_naive_timestamps_are_refused(calendar):
    with pytest.raises(ValueError):
        CorporateAction("SEM", SEM_DEAL.kind, date(2025, 12, 1), date(2026, 7, 1), datetime(2025, 12, 1))
    with pytest.raises(ValueError):
        check_tradable("AAPL", date(2026, 7, 2), standard_master(), standard_actions(), calendar,
                       intent=Intent.OPEN, as_of=datetime(2026, 7, 2, 14, 0))
    from the_reef.market.instruments import InstrumentRecord, InstrumentStatus
    with pytest.raises(ValueError):
        InstrumentRecord("X", "NYSE", InstrumentStatus.ACTIVE, date(2020, 1, 2), None, None, "t", datetime(2020, 1, 2))


# --- settlement identity and idempotency -------------------------------------------------------

def settle(holder="sleeve-a", already=(), actions=None, holdings=None):
    return settlements_due(
        holdings or {"SEM": 100}, actions or standard_actions(), date(2026, 7, 2),
        holder=holder, as_of=datetime(2026, 7, 2, 14, 0, tzinfo=UTC), already_settled=already,
    )


def test_settlement_event_id_is_stable_across_runs():
    assert settle()[0].event_id == settle()[0].event_id


def test_settlement_is_idempotent_given_the_ledgers_recorded_ids():
    [event] = settle()
    assert settle(already={event.event_id}) == []
    assert settle(already={"some-other-event"}) != []


def test_event_id_survives_restated_terms_and_duplicate_source_rows():
    restated = replace(SEM_DEAL, known_at=datetime(2026, 6, 15, tzinfo=UTC), evidence=("other-filing",))
    [event] = settle()
    [again] = settle(actions=StaticCorporateActions([SEM_DEAL, SEM_DEAL, restated]))
    assert again.event_id == event.event_id
    assert len(settle(actions=StaticCorporateActions([SEM_DEAL, SEM_DEAL]))) == 1


def test_event_ids_are_distinct_per_holder_and_per_action():
    assert settle("sleeve-a")[0].event_id != settle("sleeve-b")[0].event_id
    other_day = replace(SEM_DEAL, effective=date(2026, 7, 2))
    assert other_day.action_id != SEM_DEAL.action_id


def test_fingerprint_changes_when_the_payload_changes_under_the_same_event_id():
    [a] = settle(holdings={"SEM": 100})
    [b] = settle(holdings={"SEM": 120})
    assert a.event_id == b.event_id and a.fingerprint != b.fingerprint
