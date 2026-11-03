"""Where the live-paper system keeps its files, and the epoch it runs.

Everything lives outside the repository (``the_reef_private`` beside it by default) because it holds vendor-derived
market rows. Override with ``REEF_LIVE_DIR`` and, to keep the checkpoints on a different drive or synced folder,
``REEF_CHECKPOINT_DIR``. Nothing in here reads a clock or the network.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from the_reef.backtest.universe import UNIVERSE

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = REPO_ROOT.parent / "the_reef_private" / "live"
DEFAULT_UI_DIR = REPO_ROOT / "dashboard" / "frontend" / "public" / "reef2" / "live"  # gitignored

EXECUTION_BASIS = "SIMULATED_FROM_DAILY_OHLC"
PROVIDER = "Yahoo Finance public chart data via yfinance (free, personal use)"


@dataclass(frozen=True)
class LivePaths:
    root: Path
    checkpoint_root: Path
    ui_dir: Path | None = None

    @property
    def market_dir(self) -> Path:
        return self.root / "market"

    def epoch_dir(self, epoch_id: str) -> Path:
        return self.root / "epochs" / epoch_id

    def ledger_file(self, epoch_id: str) -> Path:
        return self.epoch_dir(epoch_id) / "ledger.jsonl"

    def lock_file(self, epoch_id: str) -> Path:
        return self.epoch_dir(epoch_id) / "ledger.lock"

    def checkpoint_file(self, epoch_id: str) -> Path:
        return self.checkpoint_root / "checkpoints" / f"{epoch_id}.jsonl"

    def backup_dir(self, epoch_id: str) -> Path:
        return self.checkpoint_root / "backups" / epoch_id

    def snapshot_file(self, epoch_id: str) -> Path:
        return self.root / "snapshots" / epoch_id / "snapshot.json"

    @property
    def runs_log(self) -> Path:
        return self.root / "runs.jsonl"


def default_paths() -> LivePaths:
    root = Path(os.environ.get("REEF_LIVE_DIR", DEFAULT_ROOT))
    cp = Path(os.environ.get("REEF_CHECKPOINT_DIR", root))
    ui = os.environ.get("REEF_LIVE_UI_DIR")
    return LivePaths(root, cp, Path(ui) if ui else DEFAULT_UI_DIR)


@dataclass(frozen=True)
class EpochSpec:
    """The epoch's identity. ``first_session`` is the first session whose close the sharks decide on."""

    epoch_id: str
    first_session: date
    initial_cash: Decimal = Decimal("10000")
    universe: tuple[str, ...] = UNIVERSE
    warmup_sessions: int = 160  # prior bars each symbol needs: strategies use up to 120, the tradability rule 60

    @staticmethod
    def for_first_session(first_session: date, initial_cash: Decimal = Decimal("10000"), **kw) -> "EpochSpec":
        return EpochSpec(f"live-paper-{first_session.isoformat()}", first_session, initial_cash, **kw)
