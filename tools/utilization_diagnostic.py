"""Capital-utilization diagnostic for the 70-session competition fixture, before and after the eligibility screen.

    uv run python tools/utilization_diagnostic.py            # print the report
    uv run python tools/utilization_diagnostic.py --write    # update docs/reef2-utilization-report.md

Offline and deterministic: synthetic prices from tests/fixtures, the real engine and ledger, no network, no Atlas, no model.
It traces every session of both pods through signal -> candidate cap -> D0 ranking -> gate -> Risk Engine -> fill, and reports
where capital stayed unused. "Before" runs the pipeline with ``screen_untradable=False`` (a name the gate would refuse can take
a candidate slot and D0's single slot); "after" runs the shipped default. The differences are consequences to inspect, not
targets: nothing here tunes a parameter or chooses a configuration for its result.

Reading the session states (one per pod and session, in this order):
  A  no strategy signal on any name
  B  signals only on names the pod already holds (v1 has no pyramiding)
  C  signals only on names the gate would refuse (untradable)
  D  a tradable signal existed and none was funded (candidate cap or D0's one new position per session)
  E  a tradable signal was funded; whatever cash remains is what sizing left
"""
from __future__ import annotations

import dataclasses
import sys
from collections import Counter
from datetime import timedelta
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.fixtures.competition_scenario import FIRST, SESSIONS, UNIVERSE, make_comp_deps, make_comp_world  # noqa: E402
from the_reef.engine.advance import DECISION_DELAY, HISTORY_BARS, advance, bootstrap  # noqa: E402
from the_reef.execution.gate import screen_candidate  # noqa: E402
from the_reef.ledger.events import EventKind  # noqa: E402
from the_reef.ledger.ledger import Ledger  # noqa: E402
from the_reef.market.instruments import Intent  # noqa: E402
from the_reef.performance.metrics import flow_adjusted_series  # noqa: E402
from the_reef.strategy.base import HoldingView, StrategyContext  # noqa: E402

D = Decimal
DOC = ROOT / "docs" / "reef2-utilization-report.md"
PODS = ("momentum", "contrarian")
STATES = {
    "A": "no signal on any name",
    "B": "signals only on names already held",
    "C": "signals only on untradable names",
    "D": "tradable signal, none funded",
    "E": "tradable signal funded",
}


def _floor(x: Decimal) -> int:
    return int(x.to_integral_value(rounding=ROUND_FLOOR))


def _uncapped(strategy: Any) -> Any:
    base = getattr(strategy, "base", strategy)
    return type(base)(dataclasses.replace(base.params, max_candidates=1000))


def run(screen: bool) -> dict[str, Any]:
    world = make_comp_world()
    deps = dataclasses.replace(make_comp_deps(world), screen_untradable=screen)
    led = Ledger()
    bootstrap(led, deps, world.calendar.session(world.days[FIRST]).open - timedelta(hours=1))
    wide = {s.sleeve_id: _uncapped(s.strategy) for s in deps.sleeves}
    sessions: list[dict[str, Any]] = []
    seen = led.state.last_seq
    for k, i in enumerate(range(FIRST, FIRST + SESSIONS), 1):
        day = world.days[i]
        advance(led, deps, day)
        evs = [e for e in led.store.read_all() if e.seq > seen]
        seen = led.state.last_seq
        ep = led.state.epoch(deps.epoch_id)
        at = world.calendar.session(day).close + DECISION_DELAY
        marked = next(e for e in evs if e.draft.kind is EventKind.SESSION_MARKED).draft.payload
        row: dict[str, Any] = {"k": k, "day": day.isoformat(), "nav": D(marked["nav"]), "pods": {}}
        for pid in PODS:
            sl = ep.sleeves[pid]
            invested = sum((D(str(marked["marks"].get(s, p.avg_cost))) * p.shares for s, p in sl.positions.items()), D(0))
            held = {s: HoldingView(p.shares, p.avg_cost, p.stop_price) for s, p in sl.positions.items()}
            bars = {s: deps.bars.history(s, at, HISTORY_BARS) for s in UNIVERSE}
            raw = {p.symbol for p in wide[pid].propose(StrategyContext(day, at, bars, {}, frozenset()))}
            unheld = {p.symbol for p in wide[pid].propose(StrategyContext(day, at, bars, held, frozenset()))}
            untradable = {s for s in unheld if (r := screen_candidate(deps.ports, s, Intent.OPEN, at)) is not None and not r.ok}
            mine = [e for e in evs if pid in (e.draft.payload.get("sleeve_id"), e.draft.payload.get("pod_id"))]
            funded = {e.draft.payload["proposal_id"].split(":")[-1] for e in mine
                      if e.draft.kind is EventKind.APEX_DECISION and e.draft.payload["outcome"] == "FUNDED"}
            tradable = unheld - untradable
            state = "A" if not raw else "B" if not unheld else "C" if not tradable else "E" if funded else "D"
            row["pods"][pid] = {
                "cash": sl.cash, "committed": ep.committed_cash(pid), "invested": invested, "state": state,
                "events": [(e.seq, e.draft.kind.value, e.draft.payload) for e in mine],
            }
        sessions.append(row)
    events = led.store.read_all()
    return {"deps": deps, "ledger": led, "events": events, "sessions": sessions, "head": led.state.head_hash}


# --- measurements ---------------------------------------------------------------------------------------------------

def funnel(res: dict[str, Any], pid: str) -> dict[str, Any]:
    ev = [e for e in res["events"] if pid in (e.draft.payload.get("sleeve_id"), e.draft.payload.get("pod_id"))]
    kind = lambda k: [e for e in ev if e.draft.kind is k]  # noqa: E731
    decisions = kind(EventKind.APEX_DECISION)
    declined = Counter(r for e in decisions if e.draft.payload["outcome"] == "DECLINED" for r in e.draft.payload["reasons"]
                       if r in ("D0_RANK_CAP", "PENDING_CASH_DEAL") or r.startswith("RISK"))
    queued = kind(EventKind.ORDER_QUEUED)
    rejected = Counter(f"{e.draft.payload['stage']}:{e.draft.payload['code']}" for e in kind(EventKind.ORDER_REJECTED))
    fills = kind(EventKind.FILL)
    return {
        "suppressed": len(kind(EventKind.OPPORTUNITY_SUPPRESSED)), "proposals": len(kind(EventKind.PROPOSAL_SUBMITTED)),
        "funded": sum(1 for e in decisions if e.draft.payload["outcome"] == "FUNDED"),
        "declined": sum(1 for e in decisions if e.draft.payload["outcome"] == "DECLINED"), "declined_by": declined,
        "queued_open": sum(1 for e in queued if e.draft.payload["intent"] == "open"),
        "queued_exit": sum(1 for e in queued if e.draft.payload["intent"] != "open"),
        "rejected": rejected, "buys": sum(1 for e in fills if e.draft.payload["side"] == "BUY"),
        "sells": sum(1 for e in fills if e.draft.payload["side"] == "SELL"),
        "bought": sum((D(e.draft.payload["price"]) * e.draft.payload["shares"] for e in fills if e.draft.payload["side"] == "BUY"), D(0)),
    }


def utilization(res: dict[str, Any], pid: str, lo: int, hi: int) -> tuple[Decimal, Decimal, Decimal]:
    rows = [r for r in res["sessions"] if lo <= r["k"] <= hi]
    u = [r["pods"][pid]["invested"] / (r["pods"][pid]["invested"] + r["pods"][pid]["cash"]) for r in rows]
    idle = [r["pods"][pid]["cash"] - r["pods"][pid]["committed"] for r in rows]
    ctrl = [r["pods"][pid]["invested"] + r["pods"][pid]["cash"] for r in rows]
    n = D(len(rows))
    return sum(u, D(0)) / n, sum(idle, D(0)) / n, sum(ctrl, D(0)) / n


def fund_invested(res: dict[str, Any]) -> tuple[Decimal, Decimal, Decimal]:
    share = [sum((r["pods"][p]["invested"] for p in PODS), D(0)) / r["nav"] for r in res["sessions"]]
    return sum(share, D(0)) / len(share), max(share), share[-1]


def states(res: dict[str, Any], pid: str, lo: int, hi: int) -> Counter:
    return Counter(r["pods"][pid]["state"] for r in res["sessions"] if lo <= r["k"] <= hi)


def sizing(res: dict[str, Any]) -> list[dict[str, Any]]:
    """For every new position: what the pod asked for, what each limit would allow, and which one set the size."""
    lim = res["deps"].limits
    nav_on = {r["day"]: r["nav"] for r in res["sessions"]}
    decisions = {e.draft.payload["order_id"]: e.draft.payload for e in res["events"]
                 if e.draft.kind is EventKind.APEX_DECISION and e.draft.payload.get("order_id")}
    fills: dict[str, int] = {}
    for e in res["events"]:
        if e.draft.kind is EventKind.FILL and e.draft.payload["side"] == "BUY":
            fills[e.draft.payload["order_id"]] = fills.get(e.draft.payload["order_id"], 0) + e.draft.payload["shares"]
    out = []
    for e in res["events"]:
        p = e.draft.payload
        if e.draft.kind is not EventKind.ORDER_QUEUED or p["intent"] != "open":
            continue
        d = decisions[p["order_id"]]
        nav, ref, stop, cash = nav_on[p["decided_at"][:10]], D(p["ref_price"]), D(p["stop_price"]), D(d["sleeve_cash"])
        by = {"risk per trade": _floor(lim.risk_per_trade_pct * nav / (ref - stop)), "position cap": _floor(lim.max_position_pct * nav / ref),
              "sleeve cash": _floor(cash / ref)}
        allowed = min(by.values())
        ask = d["requested_shares"]
        binding = "request fraction" if ask < allowed else min(by, key=lambda k: (by[k], list(by).index(k)))
        out.append({"seq": e.seq, "pod": p["sleeve_id"], "symbol": p["symbol"], "day": p["decided_at"][:10], "ask": ask, "allowed": allowed,
                    "filled": fills.get(p["order_id"], 0), "binding": binding, "price": ref})
    return out


def reviews(res: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"seq": e.seq, **e.draft.payload} for e in res["events"] if e.draft.kind is EventKind.APEX_CAPITAL_DECISION]


def returns(res: dict[str, Any]) -> dict[str, Decimal]:
    out = {"fund": res["sessions"][-1]["nav"] / D(10000) - 1}
    for pid in PODS:
        pts = flow_adjusted_series(res["events"], res["deps"].epoch_id, pid)
        out[pid] = pts[-1].index - 1
    return out


# --- the report -----------------------------------------------------------------------------------------------------

def usd(x: Decimal | int) -> str:
    return f"${x:,.0f}"


def pc(x: Decimal) -> str:
    return f"{x * 100:.1f}%"


def counts(c: Counter) -> str:
    return ", ".join(f"{v} {k}" for k, v in sorted(c.items())) or "none"


def render() -> str:
    before, after = run(False), run(True)
    out: list[str] = []
    w = out.append
    w("# Reef 2.0: capital utilization, before and after the eligibility screen\n")
    w("Generated by `tools/utilization_diagnostic.py` from two real runs of the engine on the 70-session synthetic competition fixture "
      "(`tests/fixtures/competition_scenario.py`). Offline, deterministic, no market data, no network, no model. "
      "**It shows how the machinery behaves on invented prices; it is not evidence of investment skill, and the differences below are "
      "consequences to inspect, not targets.** No parameter was tuned to produce them.\n")
    w("- **Before**: `screen_untradable=False`. A name the gate would refuse (DEAL, a pending cash acquisition) can take one of a strategy's "
      "`max_candidates` places and D0's single new-position slot, and is then declined by the gate.")
    w("- **After** (the shipped default): such a name is withheld before ranking and recorded as `OPPORTUNITY_SUPPRESSED`. "
      "Same strategies, same ranking, same D0 slot, same Risk Engine limits, same C1 policy.")
    w(f"- Ledger heads: before `{before['head'][:12]}`, after `{after['head'][:12]}`.\n")

    w("## 1. The funnel, per pod\n")
    w("| | Momentum before | Momentum after | Contrarian before | Contrarian after |\n|---|---|---|---|---|")
    fb, fa = {p: funnel(before, p) for p in PODS}, {p: funnel(after, p) for p in PODS}
    for label, f in [
        ("Signals withheld as untradable (audit events)", lambda x: x["suppressed"]),
        ("Proposals shown to Apex", lambda x: x["proposals"]),
        ("Apex funded", lambda x: x["funded"]),
        ("Apex declined", lambda x: x["declined"]),
        ("  of which, by reason", lambda x: counts(x["declined_by"])),
        ("Entry orders queued", lambda x: x["queued_open"]),
        ("Exit orders queued", lambda x: x["queued_exit"]),
        ("Order rejections (stage:code)", lambda x: counts(x["rejected"])),
        ("Buy fills / sell fills", lambda x: f"{x['buys']} / {x['sells']}"),
        ("Dollars bought", lambda x: usd(x["bought"])),
    ]:
        w(f"| {label} | {f(fb['momentum'])} | {f(fa['momentum'])} | {f(fb['contrarian'])} | {f(fa['contrarian'])} |")
    w("\nOrders queued but not filled: "
      + ", ".join(f"{lab} {sum(1 for e in r['events'] if e.draft.kind is EventKind.ORDER_QUEUED) - sum(1 for e in r['events'] if e.draft.kind is EventKind.FILL and not e.draft.payload['order_id'].startswith('stop:'))}"
                  for lab, r in (("before", before), ("after", after)))
      + " (queued orders minus non-stop fills; stop exits are not queued).\n")

    w("## 2. What bound each new position\n")
    w("The pod asks for a fraction of its sleeve cash; D0 sets a ceiling; the Risk Engine takes the smallest of risk-per-trade, "
      "position cap and cash. 'Request fraction' means the pod asked for less than every limit would have allowed.\n")
    for label, r in (("Before", before), ("After", after)):
        s = sizing(r)
        c = Counter(x["binding"] for x in s)
        w(f"**{label}**: {len(s)} entries; binding: {counts(c)}. Asked {usd(sum(x['ask'] * x['price'] for x in s))}, "
          f"limits allowed {usd(sum(x['allowed'] * x['price'] for x in s))}, filled {usd(sum(x['filled'] * x['price'] for x in s))}.\n")

    w("## 3. Capital reviews and transfers\n")
    w("| review | session | outcome | reason | transfer | proposals counted (Momentum / Contrarian) |\n|---|---|---|---|---|---|")
    for label, r in (("before", before), ("after", after)):
        for rv in reviews(r):
            moved = ", ".join(f"{t['sleeve_id']} {D(t['amount']):+,.2f}" for t in rv["transfers"]) or "none"
            ev = rv["evidence"]
            w(f"| {label} {rv['review_id']} (#{rv['seq']}) | {rv['session_day']} | {rv['outcome']} | {', '.join(rv['reasons'])} | {moved} | "
              f"{ev['momentum']['proposals']} / {ev['contrarian']['proposals']} |")
    w("\n**Do untradable opportunities count toward C1's proposal-quality threshold?** No. C1 counts `PROPOSAL_SUBMITTED` events, "
      "the proposals Apex was shown, in the trailing window. A withheld signal is an `OPPORTUNITY_SUPPRESSED` event, never a proposal, so "
      "it cannot help a pod reach `min_proposals`. Before the correction a pending-deal name *was* submitted (and then declined by the "
      "gate), so it padded the count: Momentum's review-035 evidence cited 11 proposals, most of them DEAL. After it, the same review "
      "cites 2, below the unchanged threshold of 3, and the policy holds with `LEADER_CANNOT_DEPLOY` instead of moving $510. That is "
      "the policy working as written on cleaner evidence; no C1 value was altered.\n")

    w("## 4. Utilization\n")
    w("Utilization is invested value over the capital a pod controls (invested plus cash) at each close; idle is uncommitted cash.\n")
    w("| pod | window | before: controlled / invested / idle | after: controlled / invested / idle |\n|---|---|---|---|")
    for pid in PODS:
        for lo, hi, lab in ((1, 15, "S1-15"), (16, 70, "S16-70"), (1, 70, "S1-70")):
            ub, ua = utilization(before, pid, lo, hi), utilization(after, pid, lo, hi)
            w(f"| {pid} | {lab} | {usd(ub[2])} / {pc(ub[0])} / {usd(ub[1])} | {usd(ua[2])} / {pc(ua[0])} / {usd(ua[1])} |")
    ib, ia = fund_invested(before), fund_invested(after)
    w(f"\nFund invested share of NAV: before mean {pc(ib[0])}, max {pc(ib[1])}, end {pc(ib[2])}; "
      f"after mean {pc(ia[0])}, max {pc(ia[1])}, end {pc(ia[2])}. The limit is 60%.\n")

    w("## 5. Why capital stayed idle: session states\n")
    w("Counts of sessions by state (letters defined in the tool's docstring). A, B and C come from the strategies' own signals, the pod's "
      "holdings and the gate's rule; D and E from what Apex funded.\n")
    w("| run | pod | window | " + " | ".join(f"{k} {v}" for k, v in STATES.items()) + " |\n|---|---|---|" + "---|" * len(STATES))
    for label, r in (("before", before), ("after", after)):
        for pid in PODS:
            for lo, hi, lab in ((1, 15, "S1-15"), (16, 70, "S16-70")):
                c = states(r, pid, lo, hi)
                w(f"| {label} | {pid} | {lab} | " + " | ".join(str(c.get(k, 0)) for k in STATES) + " |")
    w("\nState D is where the defect showed: a tradable name signalled and nothing was funded because an untradable one held the place.")
    w("\n## 6. Withheld opportunities (after)\n")
    sup = [e for e in after["events"] if e.draft.kind is EventKind.OPPORTUNITY_SUPPRESSED]
    by = Counter((e.draft.payload["sleeve_id"], e.draft.payload["symbol"], e.draft.payload["reason"]) for e in sup)
    w("| pod | instrument | reason | signals withheld | first (ledger #, decision date) | last |\n|---|---|---|---|---|---|")
    for (pod, sym, reason), n in sorted(by.items()):
        mine = [e for e in sup if (e.draft.payload["sleeve_id"], e.draft.payload["symbol"], e.draft.payload["reason"]) == (pod, sym, reason)]
        f, l = mine[0], mine[-1]
        w(f"| {pod} | {sym} | {reason} | {n} | #{f.seq}, {f.draft.payload['session_day']} | #{l.seq}, {l.draft.payload['session_day']} |")
    w("\nEach record carries the instrument, the strategy's score, reference price, stop and rationale, the gate's reason and evidence, and "
      "the decision time. The first record, in full:\n")
    first = sup[0]
    w("```")
    for key in ("sleeve_id", "symbol", "session_day", "decided_at", "rule", "intent", "reason", "detail", "counted_as_proposal"):
        w(f"{key}: {first.draft.payload[key]}")
    for key, val in first.draft.payload["signal"].items():
        w(f"signal.{key}: {val}")
    w("```\n")

    w("## 7. Outcomes (inspect, do not optimize)\n")
    rb, ra = returns(before), returns(after)
    w("| | before | after |\n|---|---|---|")
    w(f"| Fund NAV, end | {usd(before['sessions'][-1]['nav'])} | {usd(after['sessions'][-1]['nav'])} |")
    for label, key in (("Fund return", "fund"), ("Momentum return (time-weighted, transfers removed)", "momentum"),
                       ("Contrarian return (time-weighted, transfers removed)", "contrarian")):
        w(f"| {label} | {rb[key] * 100:+.2f}% | {ra[key] * 100:+.2f}% |")
    w("\nThese come from invented prices over 70 sessions and a handful of trades per pod. A difference between the two columns is "
      "not a finding about the strategies.")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> str:
    return render()


if __name__ == "__main__":
    text = main()
    if "--write" in sys.argv:
        DOC.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {DOC}")
    else:
        print(text)
