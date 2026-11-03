"""The daily runner: refresh the data, then advance the engine through every finalized session not yet processed.

``run`` is safe to call at any time, as often as you like, from a scheduler or by hand:

* It takes the single-writer lock, loads the ledger (chain and preserved checkpoints verified) and compares the code
  against the epoch's CHARTER. Any failure there is a SAFE_HOLD and nothing is written.
* It advances one session at a time, strictly in order, so a skipped day is caught up in sequence and decides exactly as
  it would have on the day (the engine only ever sees bars that had closed by each decision time).
* A session is processed only when its data is final and complete (``assess_session``). Otherwise the run reports WAITING
  and leaves the ledger alone.
* Before the engine touches a session, a SESSION_DATA attestation records the digest of the bars it will use, the
  execution basis and what is missing. Without that record, no fill or mark for the session can exist.
* An interrupted run resumes mid-session: the engine appends only what is missing (see ``engine.advance``).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from the_reef.backtest import cache
from the_reef.backtest.universe import BENCHMARK
from the_reef.engine.advance import EngineError, advance, next_session_to_advance
from the_reef.ledger import events as ev
from the_reef.ledger.ledger import Ledger
from the_reef.ledger.state import LedgerError
from the_reef.live import market
from the_reef.live.config import EXECUTION_BASIS, EpochSpec, LivePaths
from the_reef.live.epoch import LiveError, Parts, build_deps, check_charter, open_ledger
from the_reef.live.store import WriterBusy, WriterLock, preserve_copy
from the_reef.market.calendar import MarketCalendar

SAFE_HOLD_KINDS = ("SPLIT", "RESTATED")  # on a held name these stop the run: its books and the vendor's prices no longer agree

EXIT = {"UP_TO_DATE": 0, "ADVANCED": 0, "ERROR": 1, "SAFE_HOLD": 2, "WAITING": 3, "NOT_ACTIVATED": 4, "BUSY": 5}


@dataclass
class RunReport:
    status: str = "UP_TO_DATE"
    processed: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    refresh: market.RefreshReport | None = None
    head_seq: int = 0
    head_hash: str = ""
    appended: int = 0
    snapshot: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return EXIT.get(self.status, 1)

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "processed": self.processed, "reasons": self.reasons, "head_seq": self.head_seq,
                "head_hash": self.head_hash, "appended": self.appended, "notes": self.notes,
                "refresh": None if self.refresh is None else {"appended": self.refresh.appended, "quarantined": self.refresh.quarantined,
                                                              "flagged": self.refresh.flagged, "holds_added": self.refresh.holds_added,
                                                              "errors": self.refresh.errors}}


def held_symbols(ledger: Ledger, epoch_id: str) -> frozenset[str]:
    ep = ledger.state.epoch(epoch_id)
    return frozenset(s for sl in ep.sleeves.values() for s in sl.positions)


def attest_session(ledger: Ledger, parts: Parts, spec: EpochSpec, paths: LivePaths, day: date, a: market.SessionAssessment,
                   now: datetime, horizon_day: date) -> bool:
    """Write the SESSION_DATA record once. Returns False when it already exists (first write wins, so a resume never rewrites it)."""
    session = parts.calendar.session(day)
    assert session is not None
    held = held_symbols(ledger, spec.epoch_id)
    close = session.close
    holds = {s: r for s in spec.universe if (r := parts.master.reasons(s, close))}
    late = parts.calendar.session_count(day, horizon_day) - 1 if horizon_day >= day else 0
    manifest = paths.market_dir / cache.MANIFEST
    draft = ev.attestation(spec.epoch_id, session.open, subtype="SESSION_DATA", key=day.isoformat(), detail={
        "session_day": day.isoformat(), "execution_basis": EXECUTION_BASIS, "data_digest": a.digest,
        "bars": a.covered, "universe": a.universe, "benchmark_present": a.benchmark, "missing": list(a.missing[:40]),
        "critical_missing": list(a.critical_missing), "holds": holds,
        "dividends_uncredited": market.dividends_on(paths.market_dir, held, day),
        "processed_at": now.isoformat(), "late_by_sessions": late, "catch_up": late > 0,
        "cache_files_digest": json.loads(manifest.read_text(encoding="utf-8")).get("files_digest", "") if manifest.exists() else "",
    })
    if draft.event_id in ledger.state.seen:
        return False
    ledger.append(draft)
    return True


def run(paths: LivePaths, spec: EpochSpec, now: datetime, *, fetcher: market.DailyFetcher | None = None,
        calendar: MarketCalendar | None = None, write_snapshot: bool = True) -> RunReport:
    rep = RunReport()
    eid = spec.epoch_id
    if not paths.ledger_file(eid).exists():
        rep.status, rep.reasons = "NOT_ACTIVATED", [f"no ledger for {eid}; the epoch has not been activated"]
        return rep
    try:
        with WriterLock(paths.lock_file(eid)):
            try:
                _run_locked(paths, spec, now, rep, fetcher, calendar, write_snapshot)
            except (LiveError, LedgerError, EngineError) as exc:
                rep.status = "SAFE_HOLD" if isinstance(exc, LiveError) else "ERROR"
                rep.reasons.append(f"{type(exc).__name__}: {exc}")
    except WriterBusy as exc:
        rep.status, rep.reasons = "BUSY", [str(exc)]
    _log_run(paths, now, rep)
    return rep


def _run_locked(paths: LivePaths, spec: EpochSpec, now: datetime, rep: RunReport, fetcher: market.DailyFetcher | None,
                calendar: MarketCalendar | None, write_snapshot: bool) -> None:
    eid = spec.epoch_id
    ledger = open_ledger(paths, eid, writable=True)
    start_seq = ledger.state.last_seq
    cal = calendar
    if fetcher is not None:
        parts0 = build_deps(paths, spec, now, cal)
        cal = parts0.calendar
        rep.refresh = market.refresh(paths.market_dir, [*spec.universe, BENCHMARK], fetcher, cal, now, held=held_symbols(ledger, eid))
    parts = build_deps(paths, spec, now, cal)
    check_charter(ledger, parts, spec)
    deps, cal = parts.deps, parts.calendar
    try:
        while True:
            horizon = market.latest_finalized_session(cal, now)
            nxt = next_session_to_advance(ledger, deps, spec.first_session)
            if horizon is None or nxt > horizon.day:
                rep.status = "ADVANCED" if rep.processed else "UP_TO_DATE"
                break
            ep = ledger.state.epoch(eid)
            session = cal.session(nxt)
            assert session is not None
            if ep.last_marked != nxt.isoformat():  # a half-finished session already passed these checks
                held = held_symbols(ledger, eid)
                blocked = [f"{s} {h.kind} ({h.detail})" for s in sorted(held) for h in parts.master.holds_for(s, session.close) if h.kind in SAFE_HOLD_KINDS]
                if blocked:
                    rep.status = "SAFE_HOLD"
                    rep.reasons.append("held position(s) whose vendor prices no longer match the books: " + "; ".join(blocked)
                                       + ". Corporate-action handling for a held name needs a human decision; nothing was advanced.")
                    break
                critical = held | {o.symbol for o in ep.pending_orders()}
                a = market.assess_session(parts.bars, cal, nxt, spec.universe, critical, now)
                if not a.ready:
                    rep.status, rep.reasons = "WAITING", [f"{nxt}: {r}" for r in a.reasons]
                    break
                attest_session(ledger, parts, spec, paths, nxt, a, now, horizon.day)
            advance(ledger, deps, nxt)
            rep.processed.append(nxt.isoformat())
    finally:
        cp = ledger.checkpoint()
        rep.head_seq, rep.head_hash = cp.seq, cp.head_hash
        rep.appended = cp.seq - start_seq
        if rep.appended:
            preserve_copy(paths.ledger_file(eid), paths.backup_dir(eid), cp.seq, cp.head_hash)
        if write_snapshot:
            from the_reef.live.snapshot import write_live_snapshot  # noqa: PLC0415

            rep.snapshot = str(write_live_snapshot(ledger, parts, spec, paths, now, run=rep))


def _log_run(paths: LivePaths, now: datetime, rep: RunReport) -> None:
    try:
        paths.runs_log.parent.mkdir(parents=True, exist_ok=True)
        with paths.runs_log.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"at": now.isoformat(), **rep.as_dict()}, sort_keys=True) + "\n")
    except OSError:
        pass  # the run log is diagnostics, not state
