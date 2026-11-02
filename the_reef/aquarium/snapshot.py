"""The engine -> aquarium contract: one JSON snapshot derived from the ledger and nothing else.

Every balance, return, decision and story in the snapshot is computed here from ledger events (plus
the point-in-time bars as price context). The page only renders it. The raw events travel with the
snapshot so the Research Lab can re-verify the hash chain and recompute the headline figures in the
browser.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Sequence

from the_reef.backtest.replay import equal_weight_series
from the_reef.engine.advance import EngineDeps
from the_reef.ledger.events import EventKind, LedgerEvent, thaw
from the_reef.ledger.ledger import InMemoryEventStore, Ledger
from the_reef.ledger.state import LedgerState, apply
from the_reef.allocation.capital import verify_capital
from the_reef.performance.metrics import flow_adjusted_series, max_drawdown, round_trips
from the_reef.pods.registry import POD_REGISTRY, PodStatus

D = Decimal
SCHEMA_VERSION = 1

DECISION_TEXT = {
    "D0_RANK_CAP": "Apex's D0 rule funds only the best-ranked idea per pod each session; this one ranked lower.",
    "SIZE_ZERO": "The sleeve's share of cash buys less than one whole share at this price.",
    "RISK_REJECTED": "The Risk Engine refused the order at the close.",
    "INSTRUMENT_NOT_TRADABLE": "The instrument is not tradable on the fill date.",
    "PENDING_CASH_DEAL": "A definitive cash acquisition is pending, so the stock is a bond with no upside (the SEM lesson).",
    "BOOK_UNTRUSTED": "A holding has no valid official close, so the book is untrusted and new exposure is blocked.",
    "POSITION_CAP": "It would exceed the 10% single-position cap.",
    "SECTOR_CAP": "It would exceed the sector exposure cap.",
}


def _money(x: Decimal) -> str:
    return format(x, "f")


def event_dict(e: LedgerEvent) -> dict[str, Any]:
    c = e.draft.content()
    return {"seq": e.seq, "prev_hash": e.prev_hash, "hash": e.hash, "event_id": c["event_id"], "epoch_id": c["epoch_id"],
            "kind": c["kind"], "occurred_at": c["occurred_at"], "payload": c["payload"]}


def _stats(points) -> dict[str, Any]:
    """Time-weighted statistics from flow-adjusted returns: a transfer of capital is never a return."""
    rets = [float(p.ret) for p in points]
    n = len(rets)
    mean = sum(rets) / n if n else 0.0
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (n - 1)) if n > 1 else 0.0
    total = float(points[-1].index - 1) if points else 0.0
    idx = [(p.day, p.index) for p in points]
    dd = float(max_drawdown(idx, D("1")))
    return {
        "return": total, "max_drawdown": dd, "sessions": n,
        "volatility_ann": sd * math.sqrt(252) if sd else None,
        "sharpe_like": (mean / sd * math.sqrt(252)) if sd else None,
        "return_over_drawdown": (total / abs(dd)) if dd < 0 else None,
    }


def _replay(events: Sequence[LedgerEvent]) -> list[tuple[LedgerEvent, LedgerState]]:
    st, out = LedgerState(), []
    for e in events:
        st = apply(st, e)
        out.append((e, st))
    return out


def build_snapshot(ledger: Ledger, deps: EngineDeps, *, first_session: date, last_session: date,
                   mode: dict[str, str]) -> dict[str, Any]:
    events = list(ledger.store.read_all())
    eid = deps.epoch_id
    stepped = _replay(events)
    final = ledger.state.epoch(eid)
    cal = deps.calendar
    initial = deps.initial_cash

    # ---- per-session series from the ledger ----------------------------------------------------------
    nav_fund: list[tuple[str, Decimal]] = []
    nav_pod: dict[str, list[tuple[str, Decimal]]] = {p.pod_id: [] for p in POD_REGISTRY}
    invested_pod: dict[str, list[Decimal]] = {p.pod_id: [] for p in POD_REGISTRY}
    marks_by_day: dict[str, dict[str, str]] = {}
    for e, st in stepped:
        if e.draft.kind is EventKind.SESSION_MARKED:
            pl = e.draft.payload
            day = str(pl["session_day"])
            nav_fund.append((day, D(str(pl["nav"]))))
            marks_by_day[day] = {k: str(v) for k, v in dict(pl["marks"]).items()}
            ep = st.epoch(eid)
            for sid, nav in dict(pl["sleeve_nav"]).items():
                nav_pod[sid].append((day, D(str(nav))))
                invested_pod[sid].append(D(str(nav)) - ep.sleeves[sid].cash)

    # ---- proposals, decisions, orders, fills -----------------------------------------------------------
    packets: dict[str, dict[str, Any]] = {}
    pk_seq: dict[str, int] = {}
    decisions: dict[str, dict[str, Any]] = {}
    dec_seq: dict[str, int] = {}
    orders: dict[tuple[str, str], dict[str, Any]] = {}
    fills: list[dict[str, Any]] = []
    stops: list[dict[str, Any]] = []
    for e in events:
        k, pl = e.draft.kind, thaw(e.draft.payload)
        if k is EventKind.PROPOSAL_SUBMITTED:
            packets[pl["proposal_id"]], pk_seq[pl["proposal_id"]] = pl, e.seq
        elif k is EventKind.APEX_DECISION:
            decisions[pl["proposal_id"]], dec_seq[pl["proposal_id"]] = pl, e.seq
        elif k is EventKind.ORDER_QUEUED:
            orders[(pl["sleeve_id"], pl["order_id"])] = {"status": "QUEUED", "seq": e.seq, **pl}
        elif k is EventKind.ORDER_REJECTED:
            o = orders.setdefault((pl["sleeve_id"], pl["order_id"]), {"seq": e.seq})
            o.update(status="REJECTED_" + pl["stage"], reject_code=pl.get("code"), reject_detail=pl.get("detail"), reject_seq=e.seq)
        elif k is EventKind.FILL:
            f = {"seq": e.seq, "at": e.draft.occurred_at.astimezone(timezone.utc).isoformat(), **pl}
            fills.append(f)
            o = orders.get((pl["sleeve_id"], pl["order_id"]))
            if o is not None:
                o["status"] = "FILLED"
        elif k is EventKind.STOP_UPDATED:
            stops.append({"seq": e.seq, **pl})

    trips = {p.pod_id: round_trips(events, eid, p.pod_id) for p in POD_REGISTRY if p.status is PodStatus.ACTIVE}
    last_day = nav_fund[-1][0] if nav_fund else last_session.isoformat()
    last_marks = {k: D(v) for k, v in marks_by_day.get(last_day, {}).items()}

    def close_path(symbol: str, a: str, b: str) -> list[list[str]]:
        out = []
        d = date.fromisoformat(a)
        end = date.fromisoformat(b)
        while d <= end:
            s = cal.session(d)
            if s is not None:
                bar = deps.bars.bar(symbol, d, s.close)
                if bar is not None:
                    out.append([d.isoformat(), _money(bar.close)])
            d = date.fromordinal(d.toordinal() + 1)
        return out

    def sleeve_nav_on(pod: str, day: str) -> Decimal | None:
        vals = [v for d, v in nav_pod[pod] if d <= day]
        return vals[-1] if vals else None

    proposal_rows = []
    for pid, pk in packets.items():
        dec = decisions.get(pid)
        pod = pk["pod_id"]
        oid = (dec or {}).get("order_id") or ""
        order = orders.get((pod, oid)) if oid else None
        row: dict[str, Any] = {
            "proposal_id": pid, "pod_id": pod, "symbol": pk["symbol"], "as_of_session": pk["as_of_session"],
            "packet": pk, "packet_seq": pk_seq[pid],
            "decision": None if dec is None else {**dec, "seq": dec_seq[pid]},
        }
        reasons = (dec or {}).get("reasons", [])
        row["decision_explained"] = [DECISION_TEXT[r] for r in reasons if r in DECISION_TEXT]
        entry = None
        if dec and dec["outcome"] == "FUNDED" and order is not None:
            row["order"] = {k: order.get(k) for k in ("order_id", "status", "fill_session", "requested_shares", "stop_price",
                                                        "seq", "reject_code", "reject_detail")}
            entry = next((f for f in fills if f["sleeve_id"] == pod and f["order_id"] == oid), None)
        if entry is not None:
            sym = pk["symbol"]
            ex = next((f for f in fills if f["sleeve_id"] == pod and f["symbol"] == sym and f["side"] == "SELL"
                       and f["seq"] > entry["seq"]), None)
            raises = [{"seq": s["seq"], "stop_price": s["stop_price"]} for s in stops
                      if s["sleeve_id"] == pod and s["symbol"] == sym and s["seq"] > entry["seq"] and (ex is None or s["seq"] < ex["seq"])]
            ex_day = ex["session_day"] if ex else last_day
            shares, entry_px = int(entry["shares"]), D(entry["price"])
            exit_px = D(ex["price"]) if ex else last_marks.get(sym)
            pnl = (exit_px - entry_px) * shares if exit_px is not None else None
            reason = None
            if ex:
                if str(ex["order_id"]).startswith("stop:"):
                    sess = cal.session(date.fromisoformat(ex["session_day"]))
                    at = datetime.fromisoformat(ex["at"])
                    reason = ("Stop hit: the stock opened below its stop, so the exit filled at the open"
                              if sess is not None and at == sess.open else "Stop hit: the stock traded down through its stop during the session")
                else:
                    reason = "Strategy exit: " + next((str(o.get("rationale", "")).split("] ", 1)[-1]
                                                       for (s, i), o in orders.items() if s == pod and i == ex["order_id"]), "exit rule")
            before = sleeve_nav_on(pod, _prev_day(nav_fund, entry["session_day"]))
            after = sleeve_nav_on(pod, ex_day)
            funded = sum((D(str(e.draft.payload["amount"])) for e in events
                          if e.draft.kind is EventKind.SLEEVE_FUNDED and e.draft.payload["sleeve_id"] == pod), D("0"))
            row["lifecycle"] = {
                "entry": {"seq": entry["seq"], "session_day": entry["session_day"], "price": entry["price"], "shares": shares,
                          "cost": _money(entry_px * shares)},
                "stop_raises": raises,
                "exit": None if ex is None else {"seq": ex["seq"], "session_day": ex["session_day"], "price": ex["price"],
                                                 "shares": int(ex["shares"]), "reason": reason},
                "status": "CLOSED" if ex else "OPEN",
                "pnl": None if pnl is None else _money(pnl.quantize(D("0.01"))),
                "return": None if pnl is None else float(pnl / (entry_px * shares)),
                "sleeve_return_contribution": None if pnl is None or before is None or before == 0 else float(pnl / before),
                "fund_return_contribution": None if pnl is None else float(pnl / initial),
                "sleeve_nav_before": None if before is None else _money(before),
                "sleeve_nav_after": None if after is None else _money(after),
                "price_path": close_path(sym, entry["session_day"], ex_day),
            }
        elif dec and dec["outcome"] == "FUNDED":
            row["lifecycle"] = {"status": "NOT_FILLED", "reason": (order or {}).get("reject_code") or "order did not fill"}
        else:
            # What the price did afterward, as a clearly hypothetical note: nothing was traded.
            pth = close_path(pk["symbol"], pk["as_of_session"], last_day)
            if len(pth) > 1:
                ref = D(pk["entry_plan"]["reference_price"])
                row["counterfactual"] = {"hypothetical": True, "ref_price": _money(ref), "last_close": pth[-1][1],
                                         "move": float(D(pth[-1][1]) / ref - 1), "through": last_day}
        proposal_rows.append(row)
    proposal_rows.sort(key=lambda r: (r["packet_seq"]))

    # ---- pods ------------------------------------------------------------------------------------------
    pods = []
    for spec in POD_REGISTRY:
        base = {"pod_id": spec.pod_id, "name": spec.name, "tagline": spec.tagline, "mandate": spec.mandate, "color": spec.color,
                "status": spec.status.value, "inactive_reason": spec.inactive_reason,
                "research_agents": list(spec.research_agents), "sleeve_weight": _money(spec.sleeve_weight)}
        if spec.status is not PodStatus.ACTIVE:
            pods.append(base)
            continue
        sl = final.sleeves[spec.pod_id]
        series = nav_pod[spec.pod_id]
        funded = sum((D(str(e.draft.payload["amount"])) for e in events
                      if e.draft.kind is EventKind.SLEEVE_FUNDED and e.draft.payload["sleeve_id"] == spec.pod_id), D("0"))
        positions = []
        unreal = D("0")
        for sym, pos in sorted(sl.positions.items()):
            mark = last_marks.get(sym, pos.avg_cost)
            unreal += mark * pos.shares - pos.cost
            positions.append({"symbol": sym, "shares": pos.shares, "avg_cost": _money(pos.avg_cost.quantize(D("0.0001"))),
                              "mark": _money(mark), "stop": None if pos.stop_price is None else _money(pos.stop_price),
                              "unrealized": _money((mark * pos.shares - pos.cost).quantize(D("0.01")))})
        last_mark_seq = max((e.seq for e in events if e.draft.kind is EventKind.SESSION_MARKED), default=0)
        after_mark = sum((D(str(e.draft.payload["amount"])) for e in events if e.seq > last_mark_seq
                          and e.draft.kind is EventKind.SLEEVE_FUNDED and e.draft.payload["sleeve_id"] == spec.pod_id), D("0"))
        nav = (series[-1][1] if series else D("0")) + after_mark  # capital controlled: a transfer made at the last close counts
        tr = trips[spec.pod_id]
        wins = [t for t in tr if t.pnl > 0]
        losses = [t for t in tr if t.pnl <= 0]
        exposure = [float(i / n) for i, (_, n) in zip(invested_pod[spec.pod_id], series) if n > 0]
        points = flow_adjusted_series(events, eid, spec.pod_id)
        stats = _stats(points)
        initial_funded = next((D(str(e.draft.payload["amount"])) for e in events
                               if e.draft.kind is EventKind.SLEEVE_FUNDED and e.draft.payload["sleeve_id"] == spec.pod_id), D("0"))
        pods.append({
            **base,
            "funded": _money(funded), "initial_funded": _money(initial_funded), "net_transfers": _money(funded - initial_funded),
            "nav": _money(nav), "twr_series": [[p.day, format(p.index, "f")] for p in points], "cash": _money(sl.cash), "invested": _money(nav - sl.cash),
            "realized_pnl": _money(sl.realized_pnl), "unrealized_pnl": _money(unreal.quantize(D("0.01"))),
            "positions": positions, "nav_series": [[d, _money(v)] for d, v in series], **stats,
            "trades": len(tr), "win_rate": (len(wins) / len(tr)) if tr else None,
            "avg_win": _money(sum((t.pnl for t in wins), D("0")) / len(wins)) if wins else None,
            "avg_loss": _money(sum((t.pnl for t in losses), D("0")) / len(losses)) if losses else None,
            "avg_exposure": sum(exposure) / len(exposure) if exposure else 0.0,
            "proposals": sum(1 for r in proposal_rows if r["pod_id"] == spec.pod_id),
            "funded_proposals": sum(1 for r in proposal_rows if r["pod_id"] == spec.pod_id and (r["decision"] or {}).get("outcome") == "FUNDED"),
            "strategy": f"{deps_strategy(deps, spec.pod_id)}",
        })
    active = [p for p in pods if p["status"] == "ACTIVE"]
    ranked = sorted(active, key=lambda p: (-(p["sharpe_like"] if p["sharpe_like"] is not None else -9e9), -p["return"]))
    for i, p in enumerate(ranked, 1):
        p["rank"] = i

    # ---- fund, benchmark, checks ----------------------------------------------------------------------
    days = [date.fromisoformat(d) for d, _ in nav_fund]
    bench = equal_weight_series(deps.bars, cal, list(deps.universe), initial, days) if days else []  # type: ignore[arg-type]
    pods_nav = sum((D(p["nav"]) for p in active), D("0"))
    fund_nav = nav_fund[-1][1] if nav_fund else initial
    capital_problems = verify_capital(events, eid)
    n_reviews = sum(1 for e in events if e.draft.kind is EventKind.APEX_CAPITAL_DECISION)
    n_moves = sum(1 for e in events if e.draft.kind is EventKind.SLEEVE_FUNDED and e.draft.payload["ref"] != "d0-initial")
    checks = [
        {"name": "Hash chain", "ok": all(e.verify() for e in events), "detail": f"{len(events)} events; each hash recomputes from its content and the previous hash"},
        {"name": "Fund NAV = unallocated cash + sleeve NAVs", "ok": final.unallocated + pods_nav == fund_nav,
         "detail": f"{_money(final.unallocated)} + {_money(pods_nav)} = {_money(fund_nav)}"},
        {"name": "Each sleeve: funded + realized + unrealized = NAV",
         "ok": all(D(p["funded"]) + D(p["realized_pnl"]) + D(p["unrealized_pnl"]) == D(p["nav"]) for p in active),
         "detail": "checked per pod from fills and the last official closes"},
        {"name": "Capital transfers verify against the ledger", "ok": not capital_problems,
         "detail": (f"{n_reviews} reviews, {n_moves} transfers: each equals its SLEEVE_FUNDED events, adds up to the reserve change, and left fund NAV alone"
                    if not capital_problems else "; ".join(capital_problems[:3]))},
        {"name": "Replaying the events reproduces the books", "ok": Ledger(InMemoryEventStore(events)).state.digest() == ledger.state.digest(),
         "detail": f"state digest {ledger.state.digest()[:16]}..."},
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "generated_from": {"epoch_id": eid, "events": len(events), "head_hash": ledger.state.head_hash,
                           "first_session": first_session.isoformat(), "last_session": last_day,
                           "initial_cash": _money(initial)},
        "limits": {"position_cap_pct": _money(deps.limits.max_position_pct * 100), "risk_per_trade_pct": _money(deps.limits.risk_per_trade_pct * 100),
                   "max_invested_pct": _money(deps.limits.max_invested_pct * 100), "daily_loss_pause_pct": _money(deps.limits.daily_loss_pause_pct * 100),
                   "drawdown_pause_pct": _money(deps.limits.drawdown_pause_pct * 100)},
        "apex": {"allocator": "D0 + capital policy C1 (deterministic)",
                 "allocation_mode": "DYNAMIC_SLEEVES" if deps.capital else "FIXED_SLEEVES", "dynamic_reallocation": deps.capital is not None,
                 "unallocated_weight": _money(D("1") - sum((p.sleeve_weight for p in POD_REGISTRY), D("0"))),
                 "sleeve_weights": {p["pod_id"]: p["sleeve_weight"] for p in pods},
                 "max_new_positions_per_pod_per_session": deps.d0.max_new_per_session,
                 "capital_policy": deps.capital.describe() if deps.capital else None,
                 "rule": "Sleeves start at 30% / 30% of the fund with 40% in the central reserve. Each session the best-ranked proposal per pod is funded with an equal share of the pod's cash as a share ceiling, then the Risk Engine sizes the order. "
                         "Every " + (str(deps.capital.review_every) if deps.capital else "-") + " sessions Apex reviews each pod's flow-adjusted record and may move one small step of uncommitted cash toward the pod that is winning."},
        "fund": {"nav": _money(fund_nav), "unallocated": _money(final.unallocated), "return": float(fund_nav / initial - 1),
                 "max_drawdown": float(max_drawdown(nav_fund, initial)),
                 "nav_series": [[d, _money(v)] for d, v in nav_fund],
                 "benchmark": {"name": "Equal-weight buy-and-hold of the fixture universe", "series": [[d, _money(v)] for d, v in bench],
                               "return": float(bench[-1][1] / initial - 1) if bench else None}},
        "pods": pods,
        "proposals": proposal_rows,
        "prices": {s: close_path(s, _first(nav_fund, 20, cal), last_day) for s in sorted({r["symbol"] for r in proposal_rows})},
        "checks": checks,
        "events": [event_dict(e) for e in events],
    }


def _prev_day(nav_fund: list[tuple[str, Decimal]], day: str) -> str:
    earlier = [d for d, _ in nav_fund if d < day]
    return earlier[-1] if earlier else day


def _first(nav_fund: list[tuple[str, Decimal]], back: int, cal) -> str:
    d = date.fromisoformat(nav_fund[0][0]) if nav_fund else date.today()
    n = 0
    while n < back:
        d = date.fromordinal(d.toordinal() - 1)
        if cal.session(d) is not None:
            n += 1
    return d.isoformat()


def deps_strategy(deps: EngineDeps, pod_id: str) -> str:
    for s in deps.sleeves:
        if s.sleeve_id == pod_id:
            return f"{s.strategy.strategy_id}@{s.strategy.spec_hash}"
    return ""
