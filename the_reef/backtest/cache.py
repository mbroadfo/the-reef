"""Local CSV cache of free historical daily bars. Lives outside the repository.

Source: Yahoo Finance public chart data via the ``yfinance`` package (already a project
dependency; no account, key or subscription). Yahoo's terms allow personal use only, so the raw
data is never committed or redistributed: the cache directory is outside the repo and only
aggregate results derived from it are published. ``Close`` is split-adjusted, not
dividend-adjusted; ``adj_close`` is kept for reference.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Sequence

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


# --- provenance manifest ------------------------------------------------------------------------------
# A manifest sits beside the private cache: where the bytes came from and a SHA-256 of every file, so a
# later replay can tell whether the data it is about to use is the data that was fetched. Only its digest
# and counts are ever published, never the rows.

MANIFEST = "manifest.json"


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def files_digest(files: dict) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_manifest(symbols: Sequence[str], source: dict, root: Path | None = None) -> dict:
    files = {}
    for sym in sorted(symbols):
        rows = read(sym, root)
        if not rows:
            continue
        files[sym] = {"rows": len(rows), "first": rows[0].day.isoformat(), "last": rows[-1].day.isoformat(),
                      "sha256": _sha256_file(path_for(sym, root))}
    return {"schema": 1, "source": source, "files": files, "files_digest": files_digest(files)}


def write_manifest(manifest: dict, root: Path | None = None) -> Path:
    p = (root or cache_dir()) / MANIFEST
    p.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return p


@dataclass(frozen=True)
class ManifestCheck:
    present: bool
    ok: bool
    checked: int = 0
    altered: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    unlisted: tuple[str, ...] = ()
    digest: str = ""
    source: dict | None = None


def verify_manifest(root: Path | None = None) -> ManifestCheck:
    base = root or cache_dir()
    mp = base / MANIFEST
    if not mp.exists():
        return ManifestCheck(False, False)
    m = json.loads(mp.read_text(encoding="utf-8"))
    files = m["files"]
    altered = tuple(sorted(s for s, f in files.items() if path_for(s, base).exists() and _sha256_file(path_for(s, base)) != f["sha256"]))
    missing = tuple(sorted(s for s in files if not path_for(s, base).exists()))
    unlisted = tuple(sorted(p.stem for p in base.glob("*.csv") if p.stem not in files))
    digest_ok = files_digest(files) == m.get("files_digest")
    ok = digest_ok and not (altered or missing or unlisted)
    return ManifestCheck(True, ok, len(files), altered, missing, unlisted, m.get("files_digest", ""), m.get("source"))
