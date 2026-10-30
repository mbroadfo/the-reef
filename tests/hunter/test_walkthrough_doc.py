"""The published walkthrough is generated from a real run; it must never drift from the engine."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_walkthrough_document_is_current():
    spec = importlib.util.spec_from_file_location("hunter_walkthrough", ROOT / "tools" / "hunter_walkthrough.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    committed = (ROOT / "docs" / "reef2-hunter-walkthrough.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert mod.main() == committed, "run: uv run python tools/hunter_walkthrough.py --write"
