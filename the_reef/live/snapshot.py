"""The live-paper snapshot: the aquarium's ordinary snapshot plus a ``live`` block saying what the page may claim.

Derived from the ledger and the vetted cache only. It carries vendor-derived prices (marks, fills, price paths), so it is
written to the private live directory and, for the local UI, to a gitignored folder. It is never committed or deployed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from the_reef.aquarium.snapshot import build_snapshot
from the_reef.backtest.universe import BENCHMARK
from the_reef.engine.advance import next_session_to_advance
from the_reef.ledger import events as ev
from the_reef.ledger.ledger import Ledger
from the_reef.live import market
from the_reef.live.config import EXECUTION_BASIS, PROVIDER, EpochSpec, LivePaths
from the_reef.live.epoch import Parts, stored_charter
from the_reef.live.store import atomic_write
from the_reef.market.calendar import classify

if TYPE_CHECKING:
    from the_reef.live.runner import RunReport

LIVE_MODE = {
    "kind": "LIVE_DATA_PAPER",
    "label": "Live-data paper trading",
    "disclosure": "Real daily market data, paper money only. Fills are simulated from the next session's daily open, high and low and "
                  "reconstructed after the close; they are not live intraday executions. Nothing is sent to a broker.",
}
DATA_STALE_AFTER = market.CRITICAL_GRACE


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat()


def live_block(ledger: Ledger, parts: Parts, spec: EpochSpec, now: datetime, run: "RunReport | None") -> dict[str, Any]:
    eid, cal, deps = spec.epoch_id, parts.calendar, parts.deps
    ep = ledger.state.epoch(eid)
    events = list(ledger.store.read_all())
    stored = stored_charter(ledger, eid) or {}
    charter = stored.get("charter", {})
    horizon = market.latest_finalized_session(cal, now)
    spy_days = parts.bars.days(BENCHMARK)
    last_bar = spy_days[-1] if spy_days else None
    behind = 0
    if horizon and (last_bar is None or last_bar < horizon.day):
        behind = cal.session_count(last_bar, horizon.day) - 1 if last_bar else -1
    if horizon is None or last_bar == (horizon.day if horizon else None):
        freshness = "CURRENT"
    elif now - market.finalized_at(horizon) > DATA_STALE_AFTER:
        freshness = "STALE"
    else:
        freshness = "AWAITING_VENDOR"
    nxt = next_session_to_advance(ledger, deps, spec.first_session)
    nxt_session = cal.session(nxt)
    phase = classify(cal, now)
    attest = [ev.thaw(e.draft.payload) for e in events if e.draft.kind is ev.EventKind.ATTESTATION and e.draft.payload.get("subtype") == "SESSION_DATA"]
    pending = [{"sleeve_id": o.sleeve_id, "symbol": o.symbol, "intent": o.intent, "shares": o.requested_shares, "fill_session": o.fill_session,
                "ref_price": format(o.ref_price, "f") if o.ref_price is not None else None,
                "stop": format(o.stop_price, "f") if o.stop_price is not None else None} for o in ep.pending_orders()]
    holds = {s: r for s in spec.universe if (r := parts.master.reasons(s, now))}
    return {
        "epoch_id": eid, "paper_only": True, "first_session": spec.first_session.isoformat(),
        "activated_at": next((e.draft.occurred_at.astimezone(timezone.utc).isoformat() for e in events if e.draft.kind is ev.EventKind.EPOCH_OPENED), None),
        "execution": {"basis": EXECUTION_BASIS, "note": charter.get("execution_note", ""),
                      "meaning": "Entry fills use the next session's official open; stops use the session's low (a gap fills at the open); "
                                 "all are reconstructed after the close from daily bars. No live intraday execution is claimed."},
        "data": {"provider": PROVIDER, "last_bar_session": last_bar.isoformat() if last_bar else None,
                 "expected_session": horizon.day.isoformat() if horizon else None, "sessions_behind": behind, "freshness": freshness,
                 "final_after_minutes": int(market.FINALIZE_DELAY.total_seconds() // 60), "checked_at": _iso(now)},
        "sessions": {"processed": len(ep.marks), "last_processed": ep.last_completed or None,
                     "next": None if nxt_session is None else {"day": nxt.isoformat(), "open": _iso(nxt_session.open), "close": _iso(nxt_session.close),
                                                               "early_close": nxt_session.early_close},
                     "market_now": phase.phase.value},
        "run": None if run is None else {"status": run.status, "reasons": run.reasons, "processed": run.processed, "at": _iso(now)},
        "holds": holds,
        "pending_orders": pending,
        "attested_sessions": len(attest),
        "catch_up_sessions": [a["session_day"] for a in attest if a.get("catch_up")],
        "uncredited_dividends": {a["session_day"]: a["dividends_uncredited"] for a in attest if a.get("dividends_uncredited")},
        "charter_hash": stored.get("charter_hash"),
    }


def build_live_snapshot(ledger: Ledger, parts: Parts, spec: EpochSpec, now: datetime, run: "RunReport | None" = None) -> dict[str, Any]:
    snap = build_snapshot(ledger, parts.deps, first_session=spec.first_session, last_session=spec.first_session, mode=LIVE_MODE)
    snap["live"] = live_block(ledger, parts, spec, now, run)
    return snap


def render(snap: dict[str, Any]) -> str:
    return json.dumps(snap, indent=1, sort_keys=True) + "\n"


def write_live_snapshot(ledger: Ledger, parts: Parts, spec: EpochSpec, paths: LivePaths, now: datetime,
                        run: "RunReport | None" = None) -> Path:
    text = render(build_live_snapshot(ledger, parts, spec, now, run))
    out = paths.snapshot_file(spec.epoch_id)
    atomic_write(out, text)
    if paths.ui_dir is not None:
        atomic_write(paths.ui_dir / "snapshot.json", text)
    return out
