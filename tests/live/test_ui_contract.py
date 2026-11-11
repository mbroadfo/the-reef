"""The live snapshot satisfies the same browser-side verifier the Research Lab runs (skipped without Node >= 22.6)."""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import date

import pytest

from tests.live.harness import Live
from the_reef.live.config import REPO_ROOT

FRONTEND = REPO_ROOT / "dashboard" / "frontend"


def node_ok() -> bool:
    node = shutil.which("node")
    if not node:
        return False
    out = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v").split(".")
    return (int(out[0]), int(out[1])) >= (22, 6)


@pytest.mark.skipif(not node_ok(), reason="needs Node >= 22.6 for --experimental-strip-types")
def test_the_browser_verifier_accepts_the_live_snapshot(tmp_path):
    lv = Live.create(tmp_path)
    lv.activate()
    lv.run_through(date(2026, 11, 3))
    env = {**os.environ, "REEF_LIVE_SNAPSHOT": str(lv.paths.snapshot_file(lv.spec.epoch_id))}
    r = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", "scripts/live.test.ts"], cwd=FRONTEND, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "sessions verified" in r.stdout


@pytest.mark.skipif(not node_ok() or not (FRONTEND / "node_modules" / "vite").exists(), reason="needs Node >= 22.6 and `npm ci` in dashboard/frontend")
def test_a_real_live_snapshot_never_reaches_a_production_build(tmp_path):
    lv = Live.create(tmp_path)
    lv.activate()
    lv.run_through(date(2026, 11, 3))
    snap = lv.paths.snapshot_file(lv.spec.epoch_id)
    assert snap.exists() and (lv.paths.ui_dir / "snapshot.json").exists()
    env = {**os.environ, "REEF_LIVE_SNAPSHOT": str(snap), "REEF_LIVE_UI_DIR": str(lv.paths.ui_dir)}
    r = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", "scripts/build-isolation.test.ts"], cwd=FRONTEND, env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr[-2000:]
    assert "absent from production build" in r.stdout


def test_the_live_ui_folder_is_ignored_by_git_and_is_not_a_public_asset():
    from the_reef.live.config import DEFAULT_UI_DIR
    assert DEFAULT_UI_DIR.relative_to(FRONTEND).parts[0] != "public"  # Vite copies public/ into every production build
    for rel in ("dashboard/frontend/.live-snapshot/snapshot.json", "dashboard/frontend/public/reef2/live/snapshot.json"):
        assert subprocess.run(["git", "check-ignore", "-q", rel], cwd=REPO_ROOT).returncode == 0
