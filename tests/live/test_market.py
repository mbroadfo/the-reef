"""Daily data: incremental refresh, provenance, validation, holds and the completeness check."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from tests.live.harness import CAL, DAYS, FIRST_INDEX, UNIVERSE, Live, Vendor, after_close, next_day, session
from the_reef.backtest import cache
from the_reef.backtest.history import HistoricalBarSource
from the_reef.live import market

D = Decimal
F = DAYS[FIRST_INDEX]
SYM = "ZFC"


def refresh(lv: Live, now, vendor=None, held=frozenset()):
    return market.refresh(lv.paths.market_dir, [*UNIVERSE, "SPY"], vendor or lv.vendor, CAL, now, held=held)


def stored(lv: Live, sym=SYM):
    return cache.read(sym, lv.paths.market_dir)


def test_seed_copies_only_warmup_rows(tmp_path):
    lv = Live.create(tmp_path)
    rows = stored(lv)
    assert rows[-1].day < F and len(rows) == FIRST_INDEX
    assert (lv.paths.market_dir / "manifest.json").exists()


def test_refresh_appends_only_final_bars_and_is_idempotent(tmp_path):
    lv = Live.create(tmp_path)
    r1 = refresh(lv, after_close(F))
    assert r1.rows == len(UNIVERSE) + 1 and not r1.errors
    assert stored(lv)[-1].day == F
    r2 = refresh(lv, after_close(F))
    assert r2.rows == 0 and stored(lv)[-1].day == F
    log = market.read_log(lv.paths.market_dir / market.INGEST)
    assert sum(1 for x in log if x["event"] == "ADDED" and x["symbol"] == SYM) == 1
    assert cache.verify_manifest(lv.paths.market_dir).ok


def test_a_bar_is_not_final_until_thirty_minutes_after_the_close(tmp_path):
    lv = Live.create(tmp_path)
    too_early = session(F).close + timedelta(minutes=10)
    r = refresh(lv, too_early)
    assert r.rows == 0 and stored(lv)[-1].day < F
    assert market.latest_finalized_session(CAL, too_early).day != F
    assert refresh(lv, session(F).close + timedelta(minutes=31)).rows > 0


def test_rows_dated_after_the_horizon_are_never_stored(tmp_path):
    lv = Live.create(tmp_path)
    refresh(lv, after_close(F))
    assert max(r.day for r in stored(lv)) == F  # the vendor holds later days; they are not yet knowable


def test_a_stale_vendor_adds_nothing_and_a_network_failure_is_an_error_not_silence(tmp_path):
    lv = Live.create(tmp_path)
    for s in [*UNIVERSE, "SPY"]:
        lv.vendor.drop(s, F)
    assert refresh(lv, after_close(F)).rows == 0
    lv.vendor.fail = True
    r = refresh(lv, after_close(F))
    assert r.rows == 0 and any("fetch failed" in e for e in r.errors)


def test_a_restated_bar_is_never_overwritten_and_puts_the_symbol_on_hold(tmp_path):
    lv = Live.create(tmp_path)
    refresh(lv, after_close(F))
    before = stored(lv)[-1]
    lv.vendor.replace(SYM, F, close=before.close * D("1.02"), high=before.high * D("1.03"))
    r = refresh(lv, after_close(next_day(F)))
    assert stored(lv)[:len(stored(lv))] and next(x for x in stored(lv) if x.day == F).close == before.close
    assert any("RESTATED" in q for q in r.quarantined) and "ZFC RESTATED" in r.holds_added
    holds = market.read_holds(lv.paths.market_dir)
    assert [(h.symbol, h.kind) for h in holds] == [(SYM, "RESTATED")]


def test_a_split_is_quarantined_and_puts_the_symbol_on_hold(tmp_path):
    lv = Live.create(tmp_path)
    refresh(lv, after_close(F))
    d2 = next_day(F)
    lv.vendor.replace(SYM, d2, split=D("2"))
    r = refresh(lv, after_close(d2))
    assert stored(lv)[-1].day == F and any("SPLIT" in q for q in r.quarantined)
    assert [h.kind for h in market.read_holds(lv.paths.market_dir)] == ["SPLIT"]
    r_again = refresh(lv, after_close(d2))  # logged once, not on every refresh
    assert not r_again.quarantined


def test_an_implausible_jump_is_quarantined_unless_the_name_is_held(tmp_path):
    for held, expect_stored in ((frozenset(), False), (frozenset({SYM}), True)):
        lv = Live.create(tmp_path / ("h" if held else "n"))
        refresh(lv, after_close(F))
        last = stored(lv)[-1]
        d2 = next_day(F)
        k = D("0.5")
        lv.vendor.replace(SYM, d2, open=last.close * k, high=last.close * k * D("1.01"), low=last.close * k * D("0.99"), close=last.close * k)
        r = refresh(lv, after_close(d2), held=held)
        assert (stored(lv)[-1].day == d2) is expect_stored
        assert bool(r.flagged) is expect_stored and bool(r.holds_added) is (not expect_stored)


def test_malformed_and_zero_volume_bars_are_refused(tmp_path):
    lv = Live.create(tmp_path)
    refresh(lv, after_close(F))
    d2 = next_day(F)
    lv.vendor.replace("ZFA", d2, volume=0)
    lv.vendor.replace("ZFB", d2, high=D("0.01"))  # high below the open and close
    r = refresh(lv, after_close(d2))
    assert any("ZFA" in q and "ZERO_VOLUME" in q for q in r.quarantined)
    assert any("ZFB" in q and "BAD_OHLC" in q for q in r.quarantined)
    assert stored(lv, "ZFA")[-1].day == F and stored(lv, "ZFC")[-1].day == d2


def test_a_late_backfill_inside_stored_history_is_not_inserted(tmp_path):
    lv = Live.create(tmp_path)
    lv.vendor.drop(SYM, F)
    refresh(lv, after_close(F))
    refresh(lv, after_close(next_day(F)))
    lv2 = Live.create(tmp_path / "b")
    assert [r.day for r in stored(lv)][-2:] == [DAYS[FIRST_INDEX - 1], next_day(F)]
    fresh_vendor = Vendor()  # the vendor now has the missing day: it must still not be spliced into history
    refresh(lv, after_close(next_day(F)), vendor=fresh_vendor)
    assert F not in [r.day for r in stored(lv)]
    assert lv2 is not None


def test_dividends_are_logged_and_reported_not_credited(tmp_path):
    lv = Live.create(tmp_path)
    lv.vendor.replace(SYM, F, dividend=D("0.42"))
    refresh(lv, after_close(F))
    assert any(x["event"] == "DIVIDEND" and x["symbol"] == SYM for x in market.read_log(lv.paths.market_dir / market.INGEST))
    assert market.dividends_on(lv.paths.market_dir, [SYM, "ZFA"], F) == {SYM: "0.42"}


def test_completeness_waits_for_the_benchmark_and_for_coverage(tmp_path):
    lv = Live.create(tmp_path)
    lv.vendor.drop("SPY", F)
    refresh(lv, after_close(F))
    bars = HistoricalBarSource(CAL, [*UNIVERSE, "SPY"], lv.paths.market_dir)
    a = market.assess_session(bars, CAL, F, UNIVERSE, [], after_close(F))
    assert a.state == "WAIT_DATA" and not a.benchmark and "SPY" in a.reasons[0]

    lv2 = Live.create(tmp_path / "b")
    for s in UNIVERSE[:3]:
        lv2.vendor.drop(s, F)
    refresh(lv2, after_close(F))
    bars2 = HistoricalBarSource(CAL, [*UNIVERSE, "SPY"], lv2.paths.market_dir)
    a2 = market.assess_session(bars2, CAL, F, UNIVERSE, [], after_close(F))
    assert a2.state == "WAIT_DATA" and a2.covered == len(UNIVERSE) - 3 and "need 95%" in a2.reasons[0]


def test_a_missing_held_symbol_waits_out_the_grace_then_fails_closed(tmp_path):
    lv = Live.create(tmp_path)
    lv.vendor.drop("ZFD", F)
    refresh(lv, after_close(F))
    bars = HistoricalBarSource(CAL, [*UNIVERSE, "SPY"], lv.paths.market_dir)
    early = market.assess_session(bars, CAL, F, UNIVERSE, ["ZFD"], after_close(F))
    late = market.assess_session(bars, CAL, F, UNIVERSE, ["ZFD"], session(F).close + market.CRITICAL_GRACE + timedelta(minutes=1))
    assert early.state == "WAIT_CRITICAL" and early.critical_missing == ("ZFD",)
    assert late.ready and late.critical_missing == ("ZFD",)  # proceeds; the engine marks it unmarked and refuses its fills


def test_three_silent_sessions_halt_a_name_but_two_do_not(tmp_path):
    lv = Live.create(tmp_path)
    for d in DAYS[FIRST_INDEX:FIRST_INDEX + 3]:
        lv.vendor.drop(SYM, d)
    for i in range(3):
        refresh(lv, after_close(DAYS[FIRST_INDEX + i]))
    bars = HistoricalBarSource(CAL, [*UNIVERSE, "SPY"], lv.paths.market_dir)
    master = market.LiveInstrumentMaster(bars, CAL, lv.paths.market_dir)
    assert master.silent_sessions(SYM, after_close(DAYS[FIRST_INDEX + 1])) == 2
    assert master.get(SYM, after_close(DAYS[FIRST_INDEX + 1])).status.value == "ACTIVE"
    assert master.get(SYM, after_close(DAYS[FIRST_INDEX + 2])).status.value == "HALTED"
    assert master.get("ZFA", after_close(DAYS[FIRST_INDEX + 2])).status.value == "ACTIVE"


def test_a_hold_applies_only_from_when_it_took_effect(tmp_path):
    lv = Live.create(tmp_path)
    refresh(lv, after_close(F))
    d2 = next_day(F)
    lv.vendor.replace(SYM, d2, split=D("2"))
    refresh(lv, after_close(d2))
    bars = HistoricalBarSource(CAL, [*UNIVERSE, "SPY"], lv.paths.market_dir)
    master = market.LiveInstrumentMaster(bars, CAL, lv.paths.market_dir)
    assert master.get(SYM, session(F).close).status.value == "ACTIVE"  # before the split: knowable then, nothing more
    assert master.get(SYM, session(d2).close).status.value == "HALTED"


def test_vetted_bars_refuse_anything_past_the_horizon(tmp_path):
    lv = Live.create(tmp_path)
    refresh(lv, after_close(F))
    inner = HistoricalBarSource(CAL, [*UNIVERSE, "SPY"], lv.paths.market_dir)
    vb = market.VettedBars(inner, DAYS[FIRST_INDEX - 1])
    far = datetime(2100, 1, 1, tzinfo=timezone.utc)
    assert vb.history(SYM, far)[-1].day == DAYS[FIRST_INDEX - 1]
    assert vb.bar(SYM, F, far) is None and vb.official_open(SYM, session(F)) is None and vb.official_close(SYM, session(F)) is None
