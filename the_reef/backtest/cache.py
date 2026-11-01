"""Local CSV cache of free historical daily bars. Lives outside the repository.

Source: Yahoo Finance public chart data via the ``yfinance`` package (already a project
dependency; no account, key or subscription). Yahoo's terms allow personal use only, so the raw
data is never committed or redistributed: the cache directory is outside the repo and only
aggregate results derived from it are published. ``Close`` is split-adjusted, not
dividend-adjusted; ``adj_close`` is kept for reference.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "the_reef_private" / "market_cache" / "yahoo"
FIELDS = ("date", "open", "high", "low", "close", "adj_close", "volume", "dividend", "split")


def cache_dir() -> Path:
    return Path(os.environ.get("REEF_MARKET_CACHE", DEFAULT_DIR))


@dataclass(frozen=True)
class RawRow:
    day: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adj_close: Decimal
    volume: int
    dividend: Decimal
    split: Decimal


def path_for(symbol: str, root: Path | None = None) -> Path:
    return (root or cache_dir()) / f"{symbol}.csv"


def write(symbol: str, rows: list[RawRow], root: Path | None = None) -> Path:
    p = path_for(symbol, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(FIELDS)
        for r in rows:
            w.writerow([r.day.isoformat(), r.open, r.high, r.low, r.close, r.adj_close, r.volume, r.dividend, r.split])
    return p


def read(symbol: str, root: Path | None = None) -> list[RawRow]:
    p = path_for(symbol, root)
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as fh:
        return [RawRow(date.fromisoformat(r["date"]), Decimal(r["open"]), Decimal(r["high"]), Decimal(r["low"]),
                       Decimal(r["close"]), Decimal(r["adj_close"]), int(r["volume"]), Decimal(r["dividend"]),
                       Decimal(r["split"])) for r in csv.DictReader(fh)]
