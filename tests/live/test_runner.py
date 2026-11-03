"""Daily operation: multi-day runs, restart, catch-up, duplicates, crashes, stale and missing data, corporate actions."""
from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tests.live.conftest import END
from tests.live.harness import CAL, DAYS, FIRST_INDEX, UNIVERSE, Live, Vendor, after_close, core, next_day, prev_day, session
from the_reef.backtest import cache
from the_reef.ledger import events as ev
from the_reef.ledger.ledger import AppendResult
from the_reef.live import epoch, market
from the_reef.live.config import EpochSpec, LivePaths
from the_reef.live.epoch import LiveError
from the_reef.live.store import FileEventStore, WriterLock
from the_reef.risk.limits import RiskLimits

D = Decimal
F = DAYS[FIRST_INDEX]
sessions_to_end = [d for d in DAYS if F <= d <= END]


def clone(lv: Live, dest) -> Live:
    """A byte-for-byte copy of a live system, as if the machine had been restored from backup."""
    shutil.copytree(lv.root, dest)
    paths = LivePaths(dest / "live", dest / "checkpoints", dest / "ui")
    return Live(dest, lv.spec, paths)


# --- activation ---------------------------------------------------------------------------------------------

def test_activation_opens_a_funded_epoch_and_invents_no_history(live):
    events = list(live.ledger().store.read_all())
    assert [e.draft.kind.value for e in events] == ["EPOCH_OPENED", "SLEEVE_CREATED", "SLEEVE_FUNDED", "SLEEVE_CREATED", "SLEEVE_FUNDED", "ATTESTATION"]
    ep = live.ledger().state.epoch()
    assert ep.initial_cash == D("10000") and ep.unallocated == D("4000")
    assert {k: v.cash for k, v in ep.sleeves.items()} == {"momentum": D("3000"), "contrarian": D("3000")}  # the existing 30/30/40
    assert not ep.marks and not ep.orders and not any(s.positions for s in ep.sleeves.values())
    assert live.spec.epoch_id == f"live-paper-{F}" and live.spec.epoch_id != "epoch-1"


def test_activation_refuses_to_backfill_to_double_open_or_to_start_without_warmup(tmp_path):
    lv = Live.create(tmp_path / "a")
    with pytest.raises(LiveError, match="already opened|not a session after"):
        epoch.activate(lv.paths, lv.spec, session(F).open + timedelta(minutes=5), CAL)
    lv.activate()
    with pytest.raises(LiveError, match="already has a ledger"):
        lv.activate()
    short = Live.create(tmp_path / "b", first_index=30)  # only 30 bars of history before the start
    with pytest.raises(LiveError, match="warmup"):
        short.activate()


def test_not_activated_means_nothing_runs(tmp_path):
    lv = Live.create(tmp_path)
    r = lv.run(after_close(F))
    assert r.status == "NOT_ACTIVATED" and r.exit_code == 4
    assert not lv.paths.ledger_file(lv.spec.epoch_id).exists()


# --- multi-day operation, holidays, early closes -----------------------------------------------------------------

def test_multi_day_run_follows_the_exchange_calendar(reference):
    ev_ = reference["events"]
    marked = [e.draft.payload["session_day"] for e in ev_ if e.draft.kind.value == "SESSION_MARKED"]
    assert marked == [d.isoformat() for d in sessions_to_end]
    assert "2026-11-26" not in marked  # Thanksgiving
    early = next(e for e in ev_ if e.draft.kind.value == "SESSION_MARKED" and e.draft.payload["session_day"] == "2026-11-27")
    assert early.draft.occurred_at.astimezone(timezone.utc).hour == 18  # 1 pm New York: marked at the early close
    assert all(r.status in ("ADVANCED", "UP_TO_DATE") and r.exit_code == 0 for r in reference["reports"])


def test_no_history_is_invented_before_the_epoch_starts(reference):
    ev_ = reference["events"]
    start = session(F).close
    for e in ev_:
        if e.draft.kind.value in ("PROPOSAL_SUBMITTED", "ORDER_QUEUED", "FILL", "SESSION_MARKED", "APEX_DECISION"):
            assert e.draft.occurred_at >= start, f"{e.draft.kind.value} #{e.seq} predates the first session's close"
    first_fill = next(e for e in ev_ if e.draft.kind.value == "FILL")
    assert first_fill.draft.occurred_at >= session(next_day(F)).open  # no fill can precede the first session's next open
    opened = next(e for e in ev_ if e.draft.kind.value == "EPOCH_OPENED")
    assert opened.draft.occurred_at < session(F).open


def test_every_fill_uses_the_next_sessions_open_and_is_labelled_reconstructed(reference):
    lv, ev_ = reference["live"], reference["events"]
    bars = {s: {r.day: r for r in cache.read(s, lv.paths.market_dir)} for s in ("momentum",) and UNIVERSE}
    attested = {e.draft.payload["session_day"]: e for e in ev_ if e.draft.kind.value == "ATTESTATION" and e.draft.payload["subtype"] == "SESSION_DATA"}
    buys = [e for e in ev_ if e.draft.kind.value == "FILL" and e.draft.payload["side"] == "BUY"]
    assert buys
    for f in buys:
        p = f.draft.payload
        day = date.fromisoformat(p["session_day"])
        assert D(p["price"]) == bars[p["symbol"]][day].open  # the vendor's open for that session, no slippage invented
        assert f.draft.occurred_at == session(day).open
        att = attested[p["session_day"]]
        assert att.seq < f.seq and att.draft.payload["execution_basis"] == "SIMULATED_FROM_DAILY_OHLC"
    charter = epoch.stored_charter(lv.ledger(), lv.spec.epoch_id)["charter"]
    assert charter["execution_basis"] == "SIMULATED_FROM_DAILY_OHLC" and "not live intraday" in charter["execution_note"]


def test_stops_gap_and_touch_fills_come_from_the_daily_bar(reference):
    lv, ev_ = reference["live"], reference["events"]
    stops = [e for e in ev_ if e.draft.kind.value == "FILL" and str(e.draft.payload["order_id"]).startswith("stop:")]
    assert stops, "the scenario includes stop exits"
    for e in stops:
        p = e.draft.payload
        day = date.fromisoformat(p["session_day"])
        bar = next(r for r in cache.read(p["symbol"], lv.paths.market_dir) if r.day == day)
        if e.draft.occurred_at == session(day).open:
            assert D(p["price"]) == bar.open <= bar.high  # gapped through: filled at the open, not at the stop
        else:
            assert bar.low <= D(p["price"]) <= bar.high  # traded through intraday


def test_the_five_ledger_checks_hold_and_the_snapshot_is_labelled_live(reference):
    lv = reference["live"]
    snap = json.loads(lv.paths.snapshot_file(lv.spec.epoch_id).read_text())
    assert all(c["ok"] for c in snap["checks"])
    assert snap["mode"]["kind"] == "LIVE_DATA_PAPER" and snap["live"]["paper_only"] is True
    assert snap["live"]["execution"]["basis"] == "SIMULATED_FROM_DAILY_OHLC"
    assert snap["live"]["data"]["freshness"] == "CURRENT" and snap["live"]["sessions"]["processed"] == len(sessions_to_end)
    assert (lv.paths.ui_dir / "snapshot.json").read_bytes() == lv.paths.snapshot_file(lv.spec.epoch_id).read_bytes()


# --- restart, catch-up, duplicates ---------------------------------------------------------------------------------------

def test_restart_in_the_middle_continues_to_the_same_ledger(reference, tmp_path):
    lv = Live.create(tmp_path)
    lv.activate()
    lv.run_through(DAYS[FIRST_INDEX + 8])
    restarted = Live(lv.root, lv.spec, LivePaths(lv.paths.root, lv.paths.checkpoint_root, lv.paths.ui_dir), Vendor())  # a new process, nothing in memory
    i = DAYS.index(DAYS[FIRST_INDEX + 8]) + 1
    while DAYS[i] <= END:
        restarted.run(after_close(DAYS[i]))
        i += 1
    assert restarted.ledger().state.head_hash == reference["head"]
    assert restarted.ledger().state.digest() == reference["digest"]


def test_skipped_days_are_caught_up_in_order_and_decide_exactly_as_on_the_day(reference, tmp_path):
    lv = Live.create(tmp_path)
    lv.activate()
    lv.run(after_close(F))
    r = lv.run(after_close(END))  # the machine was off for every session in between
    assert r.status == "ADVANCED" and r.processed == [d.isoformat() for d in sessions_to_end[1:]]
    assert core(lv.ledger().store.read_all()) == core(reference["events"])
    att = [e.draft.payload for e in lv.kinds("ATTESTATION") if e.draft.payload["subtype"] == "SESSION_DATA"]
    assert att[0]["catch_up"] is False and all(a["catch_up"] for a in att[1:-1]) and att[-1]["late_by_sessions"] == 0
    snap = json.loads(lv.paths.snapshot_file(lv.spec.epoch_id).read_text())
    assert len(snap["live"]["catch_up_sessions"]) == len(sessions_to_end) - 2


def test_a_weekend_and_a_holiday_gap_need_no_catch_up(live):
    for d in (DAYS[FIRST_INDEX], DAYS[FIRST_INDEX + 1]):
        assert live.run(after_close(d)).status == "ADVANCED"
    nxt = live.run(session(DAYS[FIRST_INDEX + 1]).close + timedelta(days=3))  # run again over a weekend: nothing new is final
    assert nxt.status in ("ADVANCED", "UP_TO_DATE", "WAITING")
    att = [e.draft.payload for e in live.kinds("ATTESTATION") if e.draft.payload["subtype"] == "SESSION_DATA"]
    assert not any(a["catch_up"] for a in att[:2])


def test_running_again_appends_nothing_and_a_duplicate_event_is_refused_quietly(live):
    live.run(after_close(F))
    head = live.ledger().state.head_hash
    for _ in range(3):
        r = live.run(after_close(F))
        assert r.status == "UP_TO_DATE" and r.appended == 0 and r.processed == []
    assert live.ledger().state.head_hash == head
    led = epoch.open_ledger(live.paths, live.spec.epoch_id, writable=True)
    first = led.store.read_all()[0].draft
    assert led.append(first) is AppendResult.DUPLICATE and led.state.head_hash == head
    ids = [e.draft.event_id for e in led.store.read_all()]
    assert len(ids) == len(set(ids))


def test_a_second_runner_is_turned_away_while_one_holds_the_lock(live):
    with WriterLock(live.paths.lock_file(live.spec.epoch_id)):
        r = live.run(after_close(F))
    assert r.status == "BUSY" and r.exit_code == 5
    assert live.ledger().state.last_seq == 6  # untouched
    assert live.run(after_close(F)).status == "ADVANCED"


# --- crashes ---------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("crash_after", [1, 3, 6, 9])
def test_a_crash_in_the_middle_of_a_session_resumes_to_the_uninterrupted_ledger(reference, tmp_path, monkeypatch, crash_after):
    first_buy = reference["first_buy"]
    crash_day = prev_day(date.fromisoformat(first_buy.draft.payload["session_day"]))  # a busy session: it queues the entry
    lv = Live.create(tmp_path)
    lv.activate()
    lv.run_through(prev_day(crash_day))

    class PowerCut(Exception):
        pass

    real, count = FileEventStore.append, {"n": 0}

    def flaky(self, event):
        count["n"] += 1
        if count["n"] > crash_after:
            with self.path.open("ab") as fh:  # half a line reaches the disk
                fh.write(b'{"seq":%d,"prev_hash":"' % event.seq)
            raise PowerCut()
        return real(self, event)

    monkeypatch.setattr(FileEventStore, "append", flaky)
    with pytest.raises(PowerCut):
        lv.run(after_close(crash_day))
    monkeypatch.undo()
    r = lv.run(after_close(crash_day))  # restart: recovers the torn line, finishes the session
    assert r.status in ("ADVANCED", "UP_TO_DATE"), r.reasons
    assert any(p.name.startswith("ledger.torn-") for p in lv.paths.epoch_dir(lv.spec.epoch_id).iterdir())
    done = list(lv.ledger().store.read_all())
    closed = next(i for i, e in enumerate(reference["events"]) if e.draft.kind.value == "SESSION_CLOSED" and e.draft.payload["session_day"] == crash_day.isoformat())
    assert [e.hash for e in done] == [e.hash for e in reference["events"][:closed + 1]]
    lv.run_through(END)  # and the epoch carries on to the identical end state
    assert lv.ledger().state.head_hash == reference["head"]


# --- stale and missing data --------------------------------------------------------------------------------------------------------

def test_stale_data_is_rejected_until_the_vendor_publishes(live):
    for s in [*UNIVERSE, "SPY"]:
        live.vendor.drop(s, F)
    seq = live.ledger().state.last_seq
    r = live.run(after_close(F))
    assert r.status == "WAITING" and r.exit_code == 3 and "SPY" in " ".join(r.reasons)
    assert live.ledger().state.last_seq == seq  # nothing recorded, nothing claimed
    snap = json.loads(live.paths.snapshot_file(live.spec.epoch_id).read_text())
    assert snap["live"]["data"]["freshness"] in ("AWAITING_VENDOR", "STALE") and snap["live"]["run"]["status"] == "WAITING"
    live.vendor = Vendor()
    assert live.run(after_close(F)).status == "ADVANCED"


def test_data_that_is_not_final_yet_is_not_used(live):
    r = live.run(session(F).close + timedelta(minutes=10))
    assert r.status == "UP_TO_DATE" and r.processed == []
    assert live.ledger().state.last_seq == 6


def test_a_network_failure_is_survived_with_what_is_already_on_disk(live):
    live.run(after_close(F))
    live.vendor.fail = True
    r = live.run(after_close(next_day(F)))
    assert r.status == "WAITING" and r.refresh.errors  # the failure is reported, the day is not processed on missing data
    live.vendor.fail = False
    assert live.run(after_close(next_day(F))).status == "ADVANCED"


def _first_trade(reference):
    p = reference["first_buy"].draft.payload
    return p["symbol"], date.fromisoformat(p["session_day"]), p["order_id"]


def test_a_missing_open_print_means_no_fill_and_no_invented_price(reference, tmp_path):
    sym, fill_day, order_id = _first_trade(reference)
    lv = Live.create(tmp_path)
    lv.activate()
    lv.run_through(prev_day(fill_day))  # the order is queued at this close
    assert any(o.symbol == sym for o in lv.ledger().state.epoch().pending_orders())
    lv.vendor.drop(sym, fill_day)
    waiting = lv.run(after_close(fill_day))
    assert waiting.status == "WAITING" and sym in " ".join(waiting.reasons)  # within the grace period it waits for the print
    r = lv.run(session(fill_day).close + market.CRITICAL_GRACE + timedelta(minutes=5))
    assert r.status == "ADVANCED"
    fills = [e for e in lv.kinds("FILL") if e.draft.payload["symbol"] == sym and e.draft.payload["session_day"] == fill_day.isoformat()]
    assert not fills
    rej = [e.draft.payload for e in lv.kinds("ORDER_REJECTED") if e.draft.payload["stage"] == "FILL" and e.draft.payload["symbol"] == sym]
    assert rej and "NO_VALID_OPEN_PRINT" in rej[0]["code"]
    assert lv.ledger().state.epoch().orders[f"{rej[0]['sleeve_id']}:{order_id}"].status.value == "REJECTED"


def test_a_missing_close_leaves_the_name_unmarked_and_blocks_new_exposure(reference, tmp_path):
    sym, fill_day, _ = _first_trade(reference)
    lv = Live.create(tmp_path)
    lv.activate()
    lv.run_through(fill_day)
    held = {s for sl in lv.ledger().state.epoch().sleeves.values() for s in sl.positions}
    assert sym in held
    day = next_day(fill_day)
    lv.vendor.drop(sym, day)
    assert lv.run(after_close(day)).status == "WAITING"
    r = lv.run(session(day).close + market.CRITICAL_GRACE + timedelta(minutes=5))
    assert r.status == "ADVANCED"
    mark = next(e.draft.payload for e in lv.kinds("SESSION_MARKED") if e.draft.payload["session_day"] == day.isoformat())
    assert sym in mark["unmarked"] and sym not in mark["marks"]
    att = next(e.draft.payload for e in lv.kinds("ATTESTATION") if e.draft.payload.get("session_day") == day.isoformat())
    assert list(att["critical_missing"]) == [sym]
    queued = [e for e in lv.kinds("ORDER_QUEUED") if e.draft.occurred_at.date() == session(day).close.date() and e.draft.payload["intent"] == "open"]
    assert not queued  # the book is untrusted, so no new exposure was queued that night
    codes = " ".join(e.draft.payload["code"] for e in lv.kinds("ORDER_REJECTED") if e.draft.payload["stage"] == "DECISION")
    assert "BOOK_UNTRUSTED" in codes or not [e for e in lv.kinds("PROPOSAL_SUBMITTED") if e.draft.occurred_at.date() == session(day).close.date()]


# --- corporate actions -------------------------------------------------------------------------------------------------------------------

def test_a_split_in_a_held_name_is_a_safe_hold_that_advances_nothing(reference, tmp_path):
    sym, fill_day, _ = _first_trade(reference)
    lv = Live.create(tmp_path)
    lv.activate()
    lv.run_through(fill_day)
    seq = lv.ledger().state.last_seq
    day = next_day(fill_day)
    lv.vendor.replace(sym, day, split=D("2"))
    r = lv.run(after_close(day))
    assert r.status == "SAFE_HOLD" and r.exit_code == 2 and sym in " ".join(r.reasons) and "SPLIT" in " ".join(r.reasons)
    assert lv.ledger().state.last_seq == seq  # no mark, no stop check, no decision on prices that no longer match the books
    again = lv.run(after_close(day))
    assert again.status == "SAFE_HOLD"
    snap = json.loads(lv.paths.snapshot_file(lv.spec.epoch_id).read_text())
    assert snap["live"]["run"]["status"] == "SAFE_HOLD" and snap["live"]["holds"][sym]


def test_a_split_in_a_name_not_held_leaves_it_out_of_the_pitch(reference, tmp_path):
    sym, fill_day, _ = _first_trade(reference)
    decide_day = prev_day(fill_day)  # the night the shark pitched this name
    lv = Live.create(tmp_path)
    lv.activate()
    lv.run_through(prev_day(decide_day))
    lv.vendor.replace(sym, decide_day, split=D("3"))
    r = lv.run(after_close(decide_day))
    assert r.status == "ADVANCED", r.reasons
    assert [h.kind for h in market.read_holds(lv.paths.market_dir)] == ["SPLIT"]
    assert not [e for e in lv.kinds("PROPOSAL_SUBMITTED") if e.draft.payload["symbol"] == sym]  # no bar, no signal, no pitch
    assert not [e for e in lv.kinds("ORDER_QUEUED") if e.draft.payload["symbol"] == sym]
    day = next_day(decide_day)
    lv.run(after_close(day))
    snap = json.loads(lv.paths.snapshot_file(lv.spec.epoch_id).read_text())
    assert "SPLIT" in snap["live"]["holds"][sym][0]
    assert not [e for e in lv.kinds("FILL") if e.draft.payload["symbol"] == sym]


def test_a_restated_name_is_suppressed_before_ranking_with_an_audit_record(reference, tmp_path):
    sym, fill_day, _ = _first_trade(reference)
    decide_day = prev_day(fill_day)
    lv = Live.create(tmp_path)
    lv.activate()
    lv.run_through(prev_day(decide_day))
    old = DAYS[DAYS.index(decide_day) - 3]
    row = next(x for x in Vendor().rows[sym] if x.day == old)
    lv.vendor.replace(sym, old, close=row.close * D("1.03"), high=row.high * D("1.04"))  # the vendor quietly re-wrote history
    assert lv.run(after_close(decide_day)).status == "ADVANCED"
    sup = [ev.thaw(e.draft.payload) for e in lv.kinds("OPPORTUNITY_SUPPRESSED") if e.draft.payload["symbol"] == sym]
    assert sup and sup[0]["reason"] == "HALTED" and "RESTATED" in " ".join(sup[0]["evidence"]) and sup[0]["counted_as_proposal"] is False
    assert not [e for e in lv.kinds("ORDER_QUEUED") if e.draft.payload["symbol"] == sym]


def test_dividends_on_held_names_are_reported_not_credited(reference, tmp_path):
    sym, fill_day, _ = _first_trade(reference)
    lv = Live.create(tmp_path)
    lv.activate()
    lv.run_through(fill_day)
    day = next_day(fill_day)
    lv.vendor.replace(sym, day, dividend=D("0.31"))
    cash_before = lv.ledger().state.epoch().cash
    assert lv.run(after_close(day)).status == "ADVANCED"
    att = next(e.draft.payload for e in lv.kinds("ATTESTATION") if e.draft.payload.get("session_day") == day.isoformat())
    assert att["dividends_uncredited"] == {sym: "0.31"}
    assert not [e for e in lv.kinds("CORPORATE_ACTION_SETTLED")]
    assert lv.ledger().state.epoch().cash == cash_before  # price-return accounting: nothing credited
    snap = json.loads(lv.paths.snapshot_file(lv.spec.epoch_id).read_text())
    assert snap["live"]["uncredited_dividends"][day.isoformat()] == {sym: "0.31"}


# --- fail closed on drift and tampering ------------------------------------------------------------------------------------------------------------

def test_changing_limits_mid_epoch_is_a_safe_hold(live, monkeypatch):
    live.run(after_close(F))
    monkeypatch.setattr(epoch, "RiskLimits", lambda: RiskLimits(max_position_pct=D("0.20")))
    r = live.run(after_close(next_day(F)))
    assert r.status == "SAFE_HOLD" and "limits" in " ".join(r.reasons)


def test_a_tampered_ledger_stops_the_run(live):
    live.run(after_close(F))
    path = live.paths.ledger_file(live.spec.epoch_id)
    text = path.read_text()
    path.write_text(text.replace('"nav":"10000', '"nav":"90000', 1))
    r = live.run(after_close(next_day(F)))
    assert r.status == "SAFE_HOLD" and "corrupt" in " ".join(r.reasons)


def test_future_bars_in_the_cache_cannot_leak_into_a_decision(live, tmp_path):
    other = Live.create(tmp_path / "clean")
    other.activate()
    other.run(after_close(F), fetch=True)
    for s in [*UNIVERSE, "SPY"]:  # poison the cache with the next day's bar, ahead of time
        rows = cache.read(s, live.paths.market_dir) + [r for r in Vendor().rows[s] if r.day in (F, next_day(F))]
        cache.write(s, rows, live.paths.market_dir)
    live.run(after_close(F), fetch=False)
    assert core(live.ledger().store.read_all()) == core(other.ledger().store.read_all())


def test_session_state_never_depends_on_the_wall_clock_after_the_fact(reference):
    for e in reference["events"]:
        if e.draft.kind.value != "ATTESTATION":
            assert "processed_at" not in json.dumps(ev.thaw(e.draft.payload))
