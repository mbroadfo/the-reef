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


def test_the_live_ui_folder_is_ignored_by_git():
    r = subprocess.run(["git", "check-ignore", "-q", "dashboard/frontend/public/reef2/live/snapshot.json"], cwd=REPO_ROOT)
    assert r.returncode == 0
