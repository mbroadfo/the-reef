"""Operate the live-data paper epoch: readiness, seeding, refresh, activation, the daily run, status and reconciliation.

    uv run --group data python tools/live.py check        # one-command readiness (read-only)
    uv run --group data python tools/live.py seed         # copy warmup history into the private live cache
    uv run --group data python tools/live.py activate --confirm <epoch-id>     # MANUAL, approved step: opens the epoch
    uv run --group data python tools/live.py run          # refresh, then process every finalized session not yet done
    uv run python tools/live.py status | reconcile | snapshot

Paper money only: no broker, no LLM, no paid service. Free daily bars via yfinance (the `data` dependency group).
Exit codes of `run`: 0 up to date or advanced, 1 error, 2 SAFE_HOLD (a human must look), 3 waiting for data, 4 not activated, 5 busy.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal

from the_reef.backtest import cache
from the_reef.live import epoch, market, readiness
from the_reef.live.config import EpochSpec, LivePaths, default_paths
from the_reef.live.reconcile import reconcile
from the_reef.live.runner import run
from the_reef.live.snapshot import write_live_snapshot
from the_reef.live.store import WriterBusy, WriterLock
from the_reef.backtest.universe import BENCHMARK, UNIVERSE


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def existing_epochs(paths: LivePaths) -> list[str]:
    d = paths.root / "epochs"
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.exists() else []


def spec_for(paths: LivePaths, args: argparse.Namespace, now: datetime, *, create: bool = False) -> EpochSpec:
    if getattr(args, "epoch_id", None):
        eid = args.epoch_id
    else:
        found = existing_epochs(paths)
        if len(found) > 1:
            sys.exit(f"several epochs exist ({', '.join(found)}); pass --epoch-id")
        eid = found[0] if found else None
    if eid:
        return EpochSpec(eid, date.fromisoformat(eid.removeprefix("live-paper-")))
    first = date.fromisoformat(args.first_session) if getattr(args, "first_session", None) else epoch.first_session_for(epoch.open_calendar(), now)
    return EpochSpec.for_first_session(first)


def cmd_check(paths: LivePaths, args: argparse.Namespace) -> int:
    now = now_utc()
    items, verdict = readiness.readiness(paths, spec_for(paths, args, now), now)
    width = max(len(i.name) for i in items)
    for i in items:
        print(f"[{i.level:4}] {i.name:<{width}}  {i.detail}")
    print(f"\nVERDICT: {verdict}")
    return 1 if verdict == "NOT READY" else 0


def cmd_seed(paths: LivePaths, args: argparse.Namespace) -> int:
    now = now_utc()
    spec = spec_for(paths, args, now)
    n = market.seed(paths.market_dir, cache.cache_dir(), [*UNIVERSE, BENCHMARK], spec.first_session)
    print(f"seeded {len(n)} symbols ({sum(n.values())} warmup rows before {spec.first_session}) into {paths.market_dir}")
    return 0 if len(n) == len(UNIVERSE) + 1 else 1


def cmd_refresh(paths: LivePaths, args: argparse.Namespace) -> int:
    now = now_utc()
    spec = spec_for(paths, args, now)
    cal = epoch.open_calendar()
    held: frozenset[str] = frozenset()
    if paths.ledger_file(spec.epoch_id).exists():
        held = frozenset(s for sl in epoch.open_ledger(paths, spec.epoch_id, writable=False).state.epoch(spec.epoch_id).sleeves.values() for s in sl.positions)
    rep = market.refresh(paths.market_dir, [*spec.universe, BENCHMARK], market.YahooFetcher(), cal, now, held=held)
    print(f"refreshed {rep.symbols} symbols: {rep.rows} new bars; quarantined {len(rep.quarantined)}; holds added {rep.holds_added or 'none'}")
    for line in [*rep.errors, *rep.flagged, *rep.quarantined[:10]]:
        print("  -", line)
    return 1 if rep.errors else 0


def cmd_activate(paths: LivePaths, args: argparse.Namespace) -> int:
    now = now_utc()
    spec = spec_for(paths, args, now, create=True)
    if args.confirm != spec.epoch_id:
        print(f"Activation opens a NEW paper epoch ({spec.epoch_id}) with ${spec.initial_cash} at 30/30/40 and starts recording decisions at the\n"
              f"close of {spec.first_session}. It trades nothing real. To proceed, repeat the command with:  --confirm {spec.epoch_id}")
        return 1
    try:
        c = epoch.activate(paths, spec, now)
    except epoch.LiveError as exc:
        print("REFUSED:", exc)
        return 1
    print(f"epoch {spec.epoch_id} is open: ${spec.initial_cash}, sleeves {c['sleeve_weights']}, first decision session {spec.first_session}")
    print("charter hash:", epoch.charter_hash(c))
    return 0


def cmd_run(paths: LivePaths, args: argparse.Namespace) -> int:
    now = now_utc()
    spec = spec_for(paths, args, now)
    rep = run(paths, spec, now, fetcher=None if args.no_refresh else market.YahooFetcher())
    print(f"{rep.status}: processed {rep.processed or 'nothing'}; ledger head #{rep.head_seq} {rep.head_hash[:12]}")
    if rep.refresh is not None:
        r = rep.refresh
        print(f"  data: {r.rows} new bars, {len(r.quarantined)} refused, holds added {r.holds_added or 'none'}" + (f", errors {r.errors}" if r.errors else ""))
    for line in rep.reasons:
        print("  -", line)
    return rep.exit_code


def cmd_status(paths: LivePaths, args: argparse.Namespace) -> int:
    now = now_utc()
    spec = spec_for(paths, args, now)
    snap = paths.snapshot_file(spec.epoch_id)
    if not snap.exists():
        print("no snapshot yet; run `live.py run` or `live.py snapshot`")
        return 4
    s = json.loads(snap.read_text(encoding="utf-8"))
    lv = s["live"]
    print(f"{lv['epoch_id']}  PAPER ONLY  basis {lv['execution']['basis']}")
    print(f"fund NAV {Decimal(s['fund']['nav']):,.2f}  return {s['fund']['return'] * 100:+.2f}%  unallocated {Decimal(s['fund']['unallocated']):,.2f}")
    for p in s["pods"]:
        if p["status"] == "ACTIVE":
            print(f"  {p['name']:11} NAV {Decimal(p['nav']):>10,.2f}  cash {Decimal(p['cash']):>10,.2f}  positions {len(p['positions'])}  trades {p['trades']}")
    d = lv["data"]
    print(f"data: last bar {d['last_bar_session']} / expected {d['expected_session']}  ({d['freshness']}, checked {d['checked_at']})")
    print(f"sessions processed {lv['sessions']['processed']}, last {lv['sessions']['last_processed']}, next {lv['sessions']['next']['day'] if lv['sessions']['next'] else '-'}")
    for o in lv["pending_orders"]:
        print(f"  queued: {o['sleeve_id']} {o['intent']} up to {o['shares']} {o['symbol']} for {o['fill_session']}")
    if lv["holds"]:
        print("holds:", "; ".join(f"{k}: {v[0]}" for k, v in lv["holds"].items()))
    if lv["run"]:
        print(f"last run: {lv['run']['status']} {lv['run']['reasons'] or ''}")
    return 0


def cmd_snapshot(paths: LivePaths, args: argparse.Namespace) -> int:
    now = now_utc()
    spec = spec_for(paths, args, now)
    try:
        with WriterLock(paths.lock_file(spec.epoch_id)):
            ledger = epoch.open_ledger(paths, spec.epoch_id, writable=False)
            parts = epoch.build_deps(paths, spec, now)
            print("wrote", write_live_snapshot(ledger, parts, spec, paths, now))
    except (WriterBusy, epoch.LiveError) as exc:
        print("REFUSED:", exc)
        return 1
    return 0


def cmd_reconcile(paths: LivePaths, args: argparse.Namespace) -> int:
    now = now_utc()
    spec = spec_for(paths, args, now)
    checks = reconcile(paths, spec, now)
    for c in checks:
        print(f"[{'ok' if c.ok else 'FAIL':4}] {c.name}: {c.detail}")
    return 0 if all(c.ok for c in checks) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--epoch-id")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "seed", "refresh", "status", "snapshot", "reconcile"):
        sub.add_parser(name)
    sub.choices["check"].add_argument("--first-session")
    sub.choices["seed"].add_argument("--first-session")
    a = sub.add_parser("activate")
    a.add_argument("--first-session")
    a.add_argument("--confirm", default="", help="the epoch id, typed back to approve opening it")
    r = sub.add_parser("run")
    r.add_argument("--no-refresh", action="store_true", help="process what is already in the cache; no network")
    args = ap.parse_args()
    return {"check": cmd_check, "seed": cmd_seed, "refresh": cmd_refresh, "activate": cmd_activate, "run": cmd_run,
            "status": cmd_status, "snapshot": cmd_snapshot, "reconcile": cmd_reconcile}[args.cmd](default_paths(), args)


if __name__ == "__main__":
    sys.exit(main())
