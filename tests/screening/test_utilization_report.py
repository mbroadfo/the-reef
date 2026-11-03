"""The committed utilization report is the output of the offline diagnostic, not hand-written."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_utilization_report_is_current():
    spec = importlib.util.spec_from_file_location("utilization_diagnostic", ROOT / "tools" / "utilization_diagnostic.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    committed = (ROOT / "docs" / "reef2-utilization-report.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert mod.render() == committed, "run: uv run python tools/utilization_diagnostic.py --write"
