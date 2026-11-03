"""Reconciliation: do the ledger, its preserved checkpoints, the data it rested on and the published snapshot all agree?

Read-only. Every check is independent and reports ``ok`` plus the evidence, so a failure says which layer disagrees.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from the_reef.backtest import cache
from the_reef.backtest.universe import BENCHMARK
from the_reef.ledger.events import EventKind
from the_reef.ledger.ledger import Ledger
from the_reef.live import market
from the_reef.live.config import EpochSpec, LivePaths
from the_reef.live.epoch import LiveError, build_deps, check_charter, open_checkpoints, open_ledger
from the_reef.live.snapshot import build_live_snapshot
from the_reef.market.calendar import MarketCalendar


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _snapshot_vs_ledger(disk: dict, ledger: Ledger, fresh: dict) -> Check:
    name = "Published snapshot agrees with the ledger"
    events = list(ledger.store.read_all())
    de = disk.get("events", [])
    if len(de) > len(events):
        return Check(name, False, f"snapshot holds {len(de)} events but the ledger only {len(events)}")
    for e, row in zip(events, de):
        if row["seq"] != e.seq or row["hash"] != e.hash:
            return Check(name, False, f"snapshot event {row['seq']} contradicts the ledger (hash differs)")
    if len(de) < len(events):
        return Check(name, False, f"snapshot is behind the ledger by {len(events) - len(de)} event(s); regenerate it (live.py snapshot)")
    problems = []
    if disk["fund"]["nav"] != fresh["fund"]["nav"]:
        problems.append(f"fund NAV {disk['fund']['nav']} vs {fresh['fund']['nav']}")
    if disk["fund"]["nav_series"] != fresh["fund"]["nav_series"]:
        problems.append("fund NAV series differs")
    for dp, fp in zip(disk["pods"], fresh["pods"]):
        for k in ("nav", "cash", "positions", "realized_pnl"):
            if dp.get(k) != fp.get(k):
                problems.append(f"{dp['pod_id']} {k} differs")
    if not all(c["ok"] for c in disk.get("checks", [])):
        problems.append("the snapshot's own checks are not all passing")
    return Check(name, not problems, "; ".join(problems) if problems else f"{len(events)} events, head {ledger.state.head_hash[:12]}, NAV {disk['fund']['nav']}")


def reconcile(paths: LivePaths, spec: EpochSpec, now: datetime, calendar: MarketCalendar | None = None) -> list[Check]:
    eid = spec.epoch_id
    out: list[Check] = []
    try:
        ledger = open_ledger(paths, eid, writable=False)
    except LiveError as exc:
        return [Check("Ledger loads, chain verifies, checkpoints match", False, str(exc))]
    events = list(ledger.store.read_all())
    cps = open_checkpoints(paths, eid)
    n_cp = len(cps.entries())
    latest = cps.latest()
    out.append(Check("Ledger loads, chain verifies, checkpoints match", True,
                     f"{len(events)} events; {n_cp} preserved checkpoints, latest seq {latest.seq if latest else 0}"
                     + ("" if latest and latest.seq == len(events) else " (ledger is ahead of the last checkpoint: the next run records it)")))
    out.append(Check("Checkpoint log chains to itself", not cps.verify_self(), "; ".join(cps.verify_self()) or "each checkpoint commits to the one before"))
    parts = build_deps(paths, spec, now, calendar)
    try:
        check_charter(ledger, parts, spec)
        out.append(Check("Code matches the epoch charter", True, "strategies, limits, Apex policy and data rules are the ones the epoch opened with"))
    except LiveError as exc:
        out.append(Check("Code matches the epoch charter", False, str(exc)))

    # Every mark and fill rests on a session whose data was attested before it was written.
    attested: dict[str, tuple[int, str]] = {}
    for e in events:
        p = e.draft.payload
        if e.draft.kind is EventKind.ATTESTATION and p.get("subtype") == "SESSION_DATA":
            attested[str(p["session_day"])] = (e.seq, str(p["data_digest"]))
    gaps = []
    for e in events:
        p = e.draft.payload
        if e.draft.kind in (EventKind.FILL, EventKind.SESSION_MARKED):
            day = str(p["session_day"])
            if day not in attested or attested[day][0] > e.seq:
                gaps.append(f"{e.draft.kind.value} #{e.seq} on {day}")
    out.append(Check("Every fill and mark follows its session's data attestation", not gaps,
                     "; ".join(gaps[:4]) if gaps else f"{len(attested)} sessions attested (execution basis SIMULATED_FROM_DAILY_OHLC)"))

    # The cache still holds the bars the sessions were decided on.
    changed = []
    for day, (_, digest) in sorted(attested.items()):
        if market.session_digest(parts.bars, [*spec.universe, BENCHMARK], datetime.fromisoformat(day).date()) != digest:
            changed.append(day)
    out.append(Check("Market cache still matches the data each session used", not changed,
                     f"bars changed after use on {', '.join(changed[:5])}" if changed else f"{len(attested)} session digests recomputed from the cache"))
    mc = cache.verify_manifest(paths.market_dir)
    out.append(Check("Market cache manifest verifies", mc.ok, "checksums match" if mc.ok else
                     f"present={mc.present} altered={list(mc.altered)[:3]} missing={list(mc.missing)[:3]} unlisted={list(mc.unlisted)[:3]}"))

    fresh = build_live_snapshot(ledger, parts, spec, now)
    out.append(Check("Snapshot's internal checks pass", all(c["ok"] for c in fresh["checks"]),
                     "; ".join(f"{c['name']}: {c['detail']}" for c in fresh["checks"] if not c["ok"]) or "chain, conservation, sleeve accounting, capital transfers, replay"))
    snap_file = paths.snapshot_file(eid)
    if not snap_file.exists():
        out.append(Check("Published snapshot agrees with the ledger", False, "no snapshot has been written yet"))
    else:
        out.append(_snapshot_vs_ledger(json.loads(snap_file.read_text(encoding="utf-8")), ledger, fresh))
    if paths.ui_dir is not None and (paths.ui_dir / "snapshot.json").exists() and snap_file.exists():
        same = (paths.ui_dir / "snapshot.json").read_bytes() == snap_file.read_bytes()
        out.append(Check("UI copy of the snapshot is the published snapshot", same, "identical bytes" if same else "the UI copy differs from the private snapshot"))
    return out


__all__ = ["Check", "reconcile"]
