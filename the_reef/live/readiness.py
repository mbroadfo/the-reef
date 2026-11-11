"""The one-command readiness check. Read-only: it never writes to the ledger, the cache or the network.

Levels: OK (good), INFO (a fact worth knowing), WARN (works, but you should look), TODO (a mandatory prerequisite
for activation that is not met yet), FAIL (broken; exit code 1).

Verdicts, from weakest to strongest claim:
  NOT READY                         something is broken (a FAIL)
  CODE READY (...)                  the code, calendar and storage work, but at least one TODO stands between you and
                                    activation (dependency, seeded warmup data, separated checkpoints...); exit code 2
  READY TO ACTIVATE (not activated) every mandatory prerequisite is satisfied; activation is still a manual, approved step
  ACTIVE                            an epoch already exists
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from the_reef.backtest import cache
from the_reef.backtest.universe import BENCHMARK
from the_reef.live import market
from the_reef.live.config import REPO_ROOT, EpochSpec, LivePaths
from the_reef.live.epoch import LiveError, build_deps, check_charter, first_session_for, open_calendar, open_ledger, warmup_shortfalls
from the_reef.live.store import WriterBusy, WriterLock
from the_reef.market.calendar import MarketCalendar

TASK_NAME = "ReefLiveDaily"


@dataclass(frozen=True)
class Item:
    name: str
    level: str
    detail: str


def _same_disk(a: Path, b: Path) -> bool:
    def probe(p: Path) -> Path:
        while not p.exists() and p != p.parent:
            p = p.parent
        return p
    try:
        return os.stat(probe(a)).st_dev == os.stat(probe(b)).st_dev
    except OSError:
        return True


def _git_ignores(path: Path) -> bool | None:
    try:
        r = subprocess.run(["git", "check-ignore", "-q", str(path / "snapshot.json")], cwd=REPO_ROOT, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.returncode == 0


def _task_installed() -> bool | None:
    if os.name != "nt":
        return None
    try:
        r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME], capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.returncode == 0


def readiness(paths: LivePaths, spec: EpochSpec | None, now: datetime, *, calendar: MarketCalendar | None = None,
              research_dir: Path | None = None, universe: tuple[str, ...] | None = None, check_scheduler: bool = True,
              has_yfinance: bool | None = None, same_disk=_same_disk) -> tuple[list[Item], str]:
    items: list[Item] = []
    add = lambda name, level, detail: items.append(Item(name, level, detail))  # noqa: E731

    # 1. tooling
    add("exchange_calendars", "OK" if importlib.util.find_spec("exchange_calendars") else "FAIL", "NYSE sessions, holidays and early closes")
    has_yf = importlib.util.find_spec("yfinance") is not None if has_yfinance is None else has_yfinance
    add("yfinance (free data fetch)", "OK" if has_yf else "TODO", "installed" if has_yf else "not installed: run `uv sync --group data` and use `uv run --group data` (required to refresh data)")

    # 2. calendar
    try:
        cal = calendar or open_calendar()
        horizon = market.latest_finalized_session(cal, now)
        add("NYSE calendar", "OK" if cal.last_day >= now.date() + timedelta(days=30) else "WARN",
            f"covers {cal.first_day}..{cal.last_day}; latest finalized session {horizon.day if horizon else 'unknown'}")
    except Exception as exc:  # noqa: BLE001
        add("NYSE calendar", "FAIL", str(exc))
        return items, "NOT READY"
    spec = spec or EpochSpec.for_first_session(first_session_for(cal, now), **({"universe": universe} if universe else {}))

    # 3. storage
    inside = REPO_ROOT in paths.root.resolve().parents or paths.root.resolve() == REPO_ROOT
    anchor = paths.root
    while not anchor.exists() and anchor != anchor.parent:
        anchor = anchor.parent
    writable = os.access(anchor, os.W_OK)  # read-only check: creates nothing
    if not writable:
        add("Live data directory", "FAIL", f"{paths.root} cannot be created: {anchor} is not writable")
    if writable:
        add("Live data directory", "FAIL" if inside else "OK", f"{paths.root}" + (" is INSIDE the repository: vendor rows must stay outside Git" if inside else " (outside the repository)"))
    if paths.ui_dir is not None and REPO_ROOT not in paths.ui_dir.resolve().parents:
        add("UI snapshot folder is gitignored", "OK", f"{paths.ui_dir} is outside the repository")
    elif paths.ui_dir is not None:
        ign = _git_ignores(paths.ui_dir)
        add("UI snapshot folder is gitignored", "OK" if ign else ("WARN" if ign is None else "FAIL"),
            f"{paths.ui_dir}" + (" (git ignores it)" if ign else " (could not confirm)" if ign is None else " is NOT ignored: vendor prices could be committed"))
    cp_anchor = paths.checkpoint_root
    while not cp_anchor.exists() and cp_anchor != cp_anchor.parent:
        cp_anchor = cp_anchor.parent
    if paths.checkpoint_root == paths.root:
        add("Checkpoints independent of the ledger", "TODO", "stored beside the ledger: set REEF_CHECKPOINT_DIR to a folder on another disk so tail truncation is detectable")
    elif same_disk(paths.checkpoint_root, paths.root):
        add("Checkpoints independent of the ledger", "TODO", f"{paths.checkpoint_root} is on the same disk as the ledger: set REEF_CHECKPOINT_DIR to another disk")
    elif REPO_ROOT in paths.checkpoint_root.resolve().parents:
        add("Checkpoints independent of the ledger", "FAIL", f"{paths.checkpoint_root} is inside the repository")
    elif not os.access(cp_anchor, os.W_OK):
        add("Checkpoints independent of the ledger", "FAIL", f"{paths.checkpoint_root} is on a different disk but cannot be written ({cp_anchor} is not writable)")
    else:
        add("Checkpoints independent of the ledger", "OK", f"{paths.checkpoint_root} is on a different disk and writable")
    free = shutil.disk_usage(paths.root if paths.root.exists() else paths.root.parent).free
    add("Disk space", "OK" if free > 1 << 30 else "WARN", f"{free / (1 << 30):.1f} GiB free")

    # 4. market data
    mdir = paths.market_dir
    if not any(mdir.glob("*.csv")) if mdir.exists() else True:
        rd = research_dir or cache.cache_dir()
        have = [s for s in [*spec.universe, BENCHMARK] if cache.path_for(s, rd).exists()]
        missing = len(spec.universe) + 1 - len(have)
        add("Live market cache", "TODO", "not seeded yet: `live.py seed` copies warmup history from the research cache")
        add("Research cache (seed source)", "OK" if not missing else "FAIL",
            f"{rd}: {len(have)} of {len(spec.universe) + 1} symbols" + (f"; missing {missing}" if missing else ""))
        if not missing:
            last = cache.read(BENCHMARK, rd)[-1].day
            add("Research cache is recent", "OK" if (spec.first_session - last).days <= 7 else "WARN", f"last {BENCHMARK} bar {last}; refresh will fill the rest after seeding")
    else:
        mc = cache.verify_manifest(mdir)
        add("Live cache manifest", "OK" if mc.ok else "FAIL", f"{mc.checked} files, digest {mc.digest[:12]}" if mc.ok else
            f"altered={list(mc.altered)[:3]} missing={list(mc.missing)[:3]} unlisted={list(mc.unlisted)[:3]}" if mc.present else "no manifest")
        parts = build_deps(paths, spec, now, cal)
        short = warmup_shortfalls(parts.bars, spec)
        add("Warmup history", "OK" if not short else "FAIL",
            f"every symbol has at least {spec.warmup_sessions} bars before {spec.first_session}" if not short else
            "short: " + ", ".join(f"{s}={n}" for s, n in sorted(short.items())[:6]))
        days = parts.bars.days(BENCHMARK)
        horizon = market.latest_finalized_session(cal, now)
        if days and horizon:
            behind = cal.session_count(days[-1], horizon.day) - 1 if days[-1] < horizon.day else 0
            add("Data freshness", "OK" if behind == 0 else "WARN", f"last {BENCHMARK} bar {days[-1]}; latest finalized session {horizon.day}"
                + ("" if behind == 0 else f" ({behind} session(s) behind: run `live.py refresh`)"))
        holds = {s: parts.master.reasons(s, now) for s in spec.universe if parts.master.reasons(s, now)}
        add("Symbols on hold", "OK" if not holds else "WARN", "none" if not holds else "; ".join(f"{s}: {r[0]}" for s, r in sorted(holds.items())[:5]))
        ing = market.read_log(mdir / market.INGEST)
        q = sum(1 for r in ing if r["event"] == "QUARANTINED")
        add("Quarantined vendor rows", "OK" if not q else "INFO", f"{q} row(s) refused so far (see ingest.jsonl)" if q else "none")

    # 5. ledger
    lf = paths.ledger_file(spec.epoch_id)
    if not lf.exists() or lf.stat().st_size == 0:
        add(f"Epoch {spec.epoch_id}", "INFO", f"NOT ACTIVATED: no ledger. First session would be {spec.first_session}. Activation is a manual, approved step.")
        verdict = "READY TO ACTIVATE (not activated)"  # downgraded below while any TODO stands
    else:
        verdict = "ACTIVE"
        try:
            ledger = open_ledger(paths, spec.epoch_id, writable=False)
            parts = build_deps(paths, spec, now, cal)
            check_charter(ledger, parts, spec)
            ep = ledger.state.epoch(spec.epoch_id)
            add(f"Epoch {spec.epoch_id}", "OK", f"{ledger.state.last_seq} events, chain and checkpoints verified, charter matches; {len(ep.marks)} sessions processed, last {ep.last_completed or 'none'}")
        except LiveError as exc:
            add(f"Epoch {spec.epoch_id}", "FAIL", str(exc))
        try:
            with WriterLock(paths.lock_file(spec.epoch_id)):
                add("Writer lock", "OK", "free (no other process is writing)")
        except WriterBusy as exc:
            add("Writer lock", "WARN", f"held: {exc}")

    # 6. scheduler
    if check_scheduler:
        inst = _task_installed()
        if inst is None:
            add("Windows scheduled task", "INFO", "not checkable on this system")
        elif inst:
            add("Windows scheduled task", "WARN", f"{TASK_NAME} IS installed: confirm unattended running was approved")
        else:
            add("Windows scheduled task", "OK", f"{TASK_NAME} is not installed: nothing runs unattended")
    todo = [i for i in items if i.level == "TODO"]
    if any(i.level == "FAIL" for i in items):
        verdict = "NOT READY"
    elif todo and verdict != "ACTIVE":
        verdict = f"CODE READY (not ready to activate: {len(todo)} prerequisite(s) open: " + "; ".join(i.name for i in todo) + ")"
    return items, verdict
