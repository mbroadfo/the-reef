"""Ledger / checkpoint / data / snapshot reconciliation, parity with the competition, readiness and the CLI."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import timedelta
from decimal import Decimal

import pytest

from tests.live.conftest import END
from tests.live.harness import CAL, DAYS, FIRST_INDEX, UNIVERSE, Live, after_close
from tests.fixtures.competition_scenario import D0_MAX_NEW, make_comp_deps, make_comp_world
from the_reef.backtest import cache
from the_reef.live import epoch, readiness
from the_reef.live.config import LivePaths
from the_reef.live.reconcile import reconcile

D = Decimal
F = DAYS[FIRST_INDEX]


def copy_of(reference, tmp_path) -> Live:
    src = reference["live"]
    shutil.copytree(src.root, tmp_path / "c")
    paths = LivePaths(tmp_path / "c" / "live", tmp_path / "c" / "checkpoints", tmp_path / "c" / "ui")
    return Live(tmp_path / "c", src.spec, paths)


def by_name(checks):
    return {c.name: c for c in checks}


def test_a_healthy_epoch_reconciles_on_every_layer(reference):
    lv = reference["live"]
    checks = reconcile(lv.paths, lv.spec, after_close(END), CAL)
    assert all(c.ok for c in checks), [c for c in checks if not c.ok]
    assert len(checks) >= 9


def test_a_snapshot_that_disagrees_with_the_ledger_is_caught(reference, tmp_path):
    lv = copy_of(reference, tmp_path)
    f = lv.paths.snapshot_file(lv.spec.epoch_id)
    snap = json.loads(f.read_text())
    snap["fund"]["nav"] = "99999.00"
    f.write_text(json.dumps(snap))
    c = by_name(reconcile(lv.paths, lv.spec, after_close(END), CAL))["Published snapshot agrees with the ledger"]
    assert not c.ok and "NAV" in c.detail


def test_a_snapshot_that_contradicts_an_event_is_caught(reference, tmp_path):
    lv = copy_of(reference, tmp_path)
    f = lv.paths.snapshot_file(lv.spec.epoch_id)
    snap = json.loads(f.read_text())
    snap["events"][40]["hash"] = "f" * 64
    f.write_text(json.dumps(snap))
    c = by_name(reconcile(lv.paths, lv.spec, after_close(END), CAL))["Published snapshot agrees with the ledger"]
    assert not c.ok and "contradicts" in c.detail


def test_a_stale_snapshot_is_reported_as_behind(reference, tmp_path):
    lv = copy_of(reference, tmp_path)
    f = lv.paths.snapshot_file(lv.spec.epoch_id)
    snap = json.loads(f.read_text())
    snap["events"] = snap["events"][:-3]
    f.write_text(json.dumps(snap))
    c = by_name(reconcile(lv.paths, lv.spec, after_close(END), CAL))["Published snapshot agrees with the ledger"]
    assert not c.ok and "behind the ledger by 3" in c.detail


def test_a_cache_edited_after_use_is_caught_two_ways(reference, tmp_path):
    lv = copy_of(reference, tmp_path)
    rows = cache.read("ZFC", lv.paths.market_dir)
    target = next(i for i, r in enumerate(rows) if r.day == DAYS[FIRST_INDEX + 3])
    rows[target] = cache.RawRow(**{**rows[target].__dict__, "close": rows[target].close * D("1.01"), "high": rows[target].high * D("1.02")})
    cache.write("ZFC", rows, lv.paths.market_dir)
    c = by_name(reconcile(lv.paths, lv.spec, after_close(END), CAL))
    assert not c["Market cache still matches the data each session used"].ok
    assert not c["Market cache manifest verifies"].ok


def test_a_truncated_ledger_is_caught_by_the_preserved_checkpoint(reference, tmp_path):
    lv = copy_of(reference, tmp_path)
    p = lv.paths.ledger_file(lv.spec.epoch_id)
    lines = p.read_bytes().split(b"\n")
    p.write_bytes(b"\n".join(lines[:-10]) + b"\n")
    checks = reconcile(lv.paths, lv.spec, after_close(END), CAL)
    assert len(checks) == 1 and not checks[0].ok and "checkpoint" in checks[0].detail


def test_a_fill_without_an_attested_session_is_flagged(reference, tmp_path):
    lv = copy_of(reference, tmp_path)
    from the_reef.ledger import events as ev
    from the_reef.live.store import FileEventStore
    p = lv.paths.ledger_file(lv.spec.epoch_id)
    events = list(FileEventStore(p).read_all())
    # Rebuild the chain without one session's attestation, as if a fill had been written with no data behind it.
    victim = next(e for e in events if e.draft.kind is ev.EventKind.ATTESTATION and e.draft.payload.get("subtype") == "SESSION_DATA"
                  and e.draft.payload["session_day"] == DAYS[FIRST_INDEX + 5].isoformat())
    from the_reef.ledger.ledger import Ledger
    forged = Ledger()
    for e in events:
        if e.seq != victim.seq:
            forged.append(e.draft)
    p.unlink()
    store = FileEventStore(p, writable=True)
    for e in forged.store.read_all():
        store.append(e)
    shutil.rmtree(lv.paths.checkpoint_root)  # a forger who also controls the checkpoints; the attestation check is the second line
    c = by_name(reconcile(lv.paths, lv.spec, after_close(END), CAL))["Every fill and mark follows its session's data attestation"]
    assert not c.ok and DAYS[FIRST_INDEX + 5].isoformat() in c.detail


# --- no new sharks, no tuning ------------------------------------------------------------------------------------------------

def test_the_live_epoch_runs_exactly_the_competition_configuration(reference):
    lv = reference["live"]
    parts = epoch.build_deps(lv.paths, lv.spec, after_close(END), CAL)
    demo = make_comp_deps(make_comp_world())
    assert [s.sleeve_id for s in parts.deps.sleeves] == [s.sleeve_id for s in demo.sleeves] == ["momentum", "contrarian"]
    assert [f"{s.strategy.strategy_id}@{s.strategy.spec_hash}" for s in parts.deps.sleeves] == [f"{s.strategy.strategy_id}@{s.strategy.spec_hash}" for s in demo.sleeves]
    assert [(s.strategy.request_fraction, s.strategy.exit_rules) for s in parts.deps.sleeves] == [(s.strategy.request_fraction, s.strategy.exit_rules) for s in demo.sleeves]
    assert parts.deps.limits == demo.limits
    assert parts.deps.capital == demo.capital and parts.deps.capital.describe()["version"] == "C1"
    assert dict(parts.deps.d0.sleeve_weights) == dict(demo.d0.sleeve_weights) == {"momentum": D("0.30"), "contrarian": D("0.30")}
    assert parts.deps.d0.max_new_per_session == demo.d0.max_new_per_session == D0_MAX_NEW
    assert parts.deps.screen_untradable is True and parts.deps.costs == demo.costs


def test_synthetic_demonstration_data_is_untouched_by_the_live_epoch(reference):
    from tools.build_competition_snapshot import DEFAULT_OUT
    snap = json.loads(DEFAULT_OUT.read_text(encoding="utf-8"))
    assert snap["mode"]["kind"] == "FIXTURE_DEMONSTRATION" and snap["generated_from"]["epoch_id"] != reference["live"].spec.epoch_id
    assert "live" not in snap


# --- readiness and the CLI ---------------------------------------------------------------------------------------------------------

def test_readiness_before_activation_says_not_activated(tmp_path):
    lv = Live.create(tmp_path)
    items, verdict = readiness.readiness(lv.paths, lv.spec, after_close(DAYS[FIRST_INDEX - 1], 120), calendar=CAL, check_scheduler=False,
                                         has_yfinance=True, same_disk=lambda a, b: False)
    assert verdict == "READY TO ACTIVATE (not activated)", [i for i in items if i.level == "FAIL"]
    assert any("NOT ACTIVATED" in i.detail for i in items)
    assert not lv.paths.ledger_file(lv.spec.epoch_id).exists()  # a check creates nothing


def test_readiness_fails_without_warmup_and_flags_missing_data(tmp_path):
    lv = Live.create(tmp_path, first_index=30)
    items, verdict = readiness.readiness(lv.paths, lv.spec, after_close(DAYS[29], 120), calendar=CAL, check_scheduler=False)
    assert verdict == "NOT READY" and any(i.name == "Warmup history" and i.level == "FAIL" for i in items)


def test_readiness_reports_a_stale_cache_and_an_active_epoch(live):
    items, verdict = readiness.readiness(live.paths, live.spec, after_close(F), calendar=CAL, check_scheduler=False)
    assert verdict == "ACTIVE" and any(i.name == "Data freshness" and i.level == "WARN" for i in items)
    assert any(i.name.startswith("Epoch live-paper") and i.level == "OK" for i in items)
    live.run(after_close(F))
    items, _ = readiness.readiness(live.paths, live.spec, after_close(F), calendar=CAL, check_scheduler=False)
    assert any(i.name == "Data freshness" and i.level == "OK" for i in items)


def test_readiness_refuses_a_data_directory_inside_the_repository(tmp_path):
    from the_reef.live.config import REPO_ROOT
    lv = Live.create(tmp_path)
    bad = LivePaths(REPO_ROOT / "tmp_live_should_not_exist", lv.paths.checkpoint_root, None)
    items, verdict = readiness.readiness(bad, lv.spec, after_close(F), calendar=CAL, check_scheduler=False)
    assert verdict == "NOT READY" and any(i.name == "Live data directory" and i.level == "FAIL" for i in items)
    assert not bad.root.exists()


def test_the_scheduled_task_is_not_installed_by_anything_here():
    inst = readiness._task_installed()
    assert inst in (False, None)


def test_activation_command_needs_the_epoch_id_typed_back(tmp_path, capsys, monkeypatch):
    import tools.live as cli
    lv = Live.create(tmp_path)
    monkeypatch.setattr(cli, "now_utc", lambda: after_close(DAYS[FIRST_INDEX - 1], 120))
    monkeypatch.setattr(epoch, "open_calendar", lambda: CAL)
    ns = argparse.Namespace(epoch_id=None, first_session=F.isoformat(), confirm="")
    assert cli.cmd_activate(lv.paths, ns) == 1 and "--confirm" in capsys.readouterr().out
    assert not lv.paths.ledger_file(lv.spec.epoch_id).exists()
    ns.confirm = "live-paper-wrong"
    assert cli.cmd_activate(lv.paths, ns) == 1
    assert not lv.paths.ledger_file(lv.spec.epoch_id).exists()
    # The real epoch id is derived from the first session; the harness epoch has a custom universe, so only the refusal path is exercised here.
    assert cli.existing_epochs(lv.paths) == []
