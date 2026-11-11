"""PR #24 review fixes: non-destructive seeding, complete charter pinning, a meaningful readiness verdict."""
from __future__ import annotations

import argparse
from decimal import Decimal

import pytest

from tests.live.harness import CAL, DAYS, FIRST_INDEX, Live, UNIVERSE, after_close
from the_reef.backtest import cache
from the_reef.live import epoch, market, readiness
from the_reef.live.config import LivePaths

D = Decimal
SYM = UNIVERSE[0]
F = DAYS[FIRST_INDEX]


def seed_again(lv: Live):
    return market.seed(lv.paths.market_dir, lv.root / "research", [*UNIVERSE, "SPY"], lv.spec.first_session,
                       epochs_dir=lv.paths.root / "epochs")


def files_of(lv: Live) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in lv.paths.market_dir.iterdir() if p.suffix in (".csv", ".json", ".jsonl")}


def do_refresh(lv: Live, now):
    return market.refresh(lv.paths.market_dir, [*UNIVERSE, "SPY"], lv.vendor, CAL, now)


# --- seeding never destroys collected data ---------------------------------------------------------------------------

def test_repeated_seeding_changes_nothing(tmp_path):
    lv = Live.create(tmp_path)
    before = files_of(lv)
    assert seed_again(lv) == {} and seed_again(lv) == {}
    assert files_of(lv) == before and cache.verify_manifest(lv.paths.market_dir).ok


def test_seeding_never_replaces_collected_live_rows(tmp_path):
    lv = Live.create(tmp_path)
    do_refresh(lv, after_close(F))
    assert cache.read(SYM, lv.paths.market_dir)[-1].day == F
    before = files_of(lv)
    assert seed_again(lv) == {}
    assert files_of(lv) == before and cache.read(SYM, lv.paths.market_dir)[-1].day == F
    assert cache.verify_manifest(lv.paths.market_dir).ok


def test_seeding_fills_only_missing_symbols(tmp_path):
    lv = Live.create(tmp_path)
    cache.path_for(SYM, lv.paths.market_dir).unlink()
    others = {k: v for k, v in files_of(lv).items() if k.endswith(".csv")}
    assert list(seed_again(lv)) == [SYM]
    assert all((lv.paths.market_dir / k).read_bytes() == v for k, v in others.items())
    assert cache.verify_manifest(lv.paths.market_dir).ok


def test_seeding_after_activation_is_refused(tmp_path):
    lv = Live.create(tmp_path)
    lv.activate()
    before = files_of(lv)
    with pytest.raises(market.SeedRefused, match="activated"):
        seed_again(lv)
    assert files_of(lv) == before


def test_seeding_over_a_tampered_cache_is_refused(tmp_path):
    lv = Live.create(tmp_path)
    p = cache.path_for(SYM, lv.paths.market_dir)
    p.write_text(p.read_text() + "\n")
    with pytest.raises(market.SeedRefused, match="manifest"):
        seed_again(lv)


def test_seed_and_refresh_cannot_interleave(tmp_path):
    lv = Live.create(tmp_path)
    before = files_of(lv)
    with market.market_lock(lv.paths.market_dir):
        with pytest.raises(market.SeedRefused, match="busy"):
            seed_again(lv)
        rep = do_refresh(lv, after_close(F))
        assert rep.rows == 0 and any("busy" in e for e in rep.errors)
    assert {k: v for k, v in files_of(lv).items() if k != "market.lock.info"} == {k: v for k, v in before.items() if k != "market.lock.info"}
    assert do_refresh(lv, after_close(F)).rows > 0  # lock released


def test_the_cli_seed_command_reports_a_refusal(tmp_path, capsys, monkeypatch):
    import tools.live as cli
    lv = Live.create(tmp_path)
    lv.activate()
    monkeypatch.setattr(cli, "now_utc", lambda: after_close(DAYS[FIRST_INDEX - 1], 120))
    monkeypatch.setattr(cache, "cache_dir", lambda: lv.root / "research")
    assert cli.cmd_seed(lv.paths, argparse.Namespace(epoch_id=lv.spec.epoch_id, first_session=F.isoformat())) == 1
    assert "refused" in capsys.readouterr().out


# --- the charter pins every behaviour-changing setting ---------------------------------------------------------------

def test_the_charter_records_request_fraction_exit_rules_and_the_desk(live):
    cfg = epoch.stored_charter(live.ledger(), live.spec.epoch_id)["charter"]["sleeve_config"]
    assert set(cfg) == {"momentum", "contrarian"}
    assert cfg["momentum"]["request_fraction"] == "0.5" and cfg["contrarian"]["request_fraction"] == "0.5"
    assert cfg["momentum"]["exit_rules"] and cfg["contrarian"]["desk"][0]["agent"] == "OversoldScout"


def drift(monkeypatch, sleeve, **changes):
    from the_reef.live import runner
    real = runner.build_deps

    def patched(*a, **k):
        parts = real(*a, **k)
        for s in parts.deps.sleeves:
            if s.sleeve_id == sleeve:
                for name, v in changes.items():
                    setattr(s.strategy, name, v)
        return parts
    monkeypatch.setattr(runner, "build_deps", patched)


def test_changing_the_request_fraction_after_activation_is_a_safe_hold(live, monkeypatch):
    live.run(after_close(F))
    seq = live.ledger().state.last_seq
    drift(monkeypatch, "momentum", request_fraction=D("0.9"))
    r = live.run(after_close(DAYS[FIRST_INDEX + 1]))
    assert r.status == "SAFE_HOLD" and r.exit_code == 2 and "sleeve_config" in " ".join(r.reasons)
    assert live.ledger().state.last_seq == seq


def test_changing_the_exit_rules_after_activation_is_a_safe_hold(live, monkeypatch):
    seq = live.ledger().state.last_seq
    drift(monkeypatch, "contrarian", exit_rules=("Exit whenever",))
    r = live.run(after_close(F))
    assert r.status == "SAFE_HOLD" and "sleeve_config" in " ".join(r.reasons)
    assert live.ledger().state.last_seq == seq


# --- the readiness verdict -------------------------------------------------------------------------------------------

def ready(lv, **kw):
    kw.setdefault("has_yfinance", True)
    kw.setdefault("same_disk", lambda a, b: False)
    return readiness.readiness(lv.paths, lv.spec, after_close(DAYS[FIRST_INDEX - 1], 120), calendar=CAL, check_scheduler=False, **kw)


def test_everything_satisfied_is_ready_to_activate(tmp_path):
    assert ready(Live.create(tmp_path))[1] == "READY TO ACTIVATE (not activated)"


@pytest.mark.parametrize("kw,name", [({"has_yfinance": False}, "yfinance"), ({"same_disk": lambda a, b: True}, "Checkpoints independent")])
def test_a_missing_prerequisite_is_code_ready_not_ready_to_activate(tmp_path, kw, name):
    items, verdict = ready(Live.create(tmp_path), **kw)
    assert verdict.startswith("CODE READY") and not verdict.startswith("READY TO ACTIVATE")
    assert any(i.level == "TODO" and i.name.startswith(name) for i in items)


def test_checkpoints_beside_the_ledger_are_not_independent(tmp_path):
    lv = Live.create(tmp_path)
    lv.paths = LivePaths(lv.paths.root, lv.paths.root, lv.paths.ui_dir)
    assert ready(lv)[1].startswith("CODE READY")


def test_an_unseeded_cache_is_code_ready(tmp_path):
    lv = Live.create(tmp_path)
    for p in lv.paths.market_dir.iterdir():
        p.unlink()
    items, verdict = ready(lv, research_dir=lv.root / "research")
    assert verdict.startswith("CODE READY") and any(i.name == "Live market cache" and i.level == "TODO" for i in items)


def test_check_stays_read_only_and_code_ready_exits_2(tmp_path, monkeypatch, capsys):
    import tools.live as cli
    lv = Live.create(tmp_path)
    monkeypatch.setattr(cli, "now_utc", lambda: after_close(DAYS[FIRST_INDEX - 1], 120))
    monkeypatch.setattr(readiness, "open_calendar", lambda: CAL)
    monkeypatch.setattr(epoch, "open_calendar", lambda: CAL)
    before = files_of(lv)
    rc = cli.cmd_check(lv.paths, argparse.Namespace(epoch_id=lv.spec.epoch_id, first_session=None))
    assert rc in (1, 2) and "VERDICT:" in capsys.readouterr().out  # never 0: checkpoints share the disk (and the real universe is not seeded)
    assert files_of(lv) == before and not lv.paths.ledger_file(lv.spec.epoch_id).exists()
