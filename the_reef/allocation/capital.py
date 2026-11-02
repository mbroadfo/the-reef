"""Apex's capital-competition policy (C1): deterministic, auditable, no model calls.

Every ``review_every`` sessions Apex judges the active pods on evidence that existed at the close, and may
move a small step of capital toward the pod that is winning. The rules are starting rules, not tuned
parameters; every number is in ``CapitalPolicy`` and is written into the ledger with each decision.

  1. Trust:     if any holding could not be marked, the books are untrusted and nothing moves.
  2. History:   a pod is judged only after ``min_history`` marked sessions. Fewer than two judged pods: hold.
  3. Score:     score = return over the last ``lookback`` sessions - 0.5 x its max drawdown, both capital-flow-adjusted
                (a transfer is never a return).
  4. Winner:    the higher score leads. A gap under ``margin`` is a draw (``flip_margin`` if it would reverse the previous
                transfer). A leader whose own score is not positive is not rewarded: least-bad is not good.
  5. Quality:   the leader must have made at least ``min_proposals`` proposals in the window, i.e. show it can use capital.
  6. Transfer:  one step (``step_pct`` of fund NAV, in whole ``round_to`` dollars) to the leader. It is taken first from the
                trailer's uncommitted cash (never below ``floor_pct`` of its initial funding, never cash promised to a
                queued order, never by selling a position), and any remainder from the central reserve (which keeps at
                least ``reserve_floor_pct`` of fund NAV). The leader never exceeds ``cap_pct`` of fund NAV.
  7. Nothing else: no liquidation, at most one transfer per review, one review every ``review_every`` sessions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, Decimal
from typing import Any, Mapping, Sequence

from the_reef.ledger.events import EventKind, LedgerEvent
from the_reef.ledger.state import EpochState
from the_reef.performance.metrics import FlowPoint, flow_adjusted_series, round_trips, window_performance

D = Decimal
CENT = D("0.01")
RATIO = D("0.000001")


@dataclass(frozen=True)
class CapitalPolicy:
    review_every: int = 10
    min_history: int = 15
    lookback: int = 20
    drawdown_weight: Decimal = D("0.5")
    margin: Decimal = D("0.02")
    flip_margin: Decimal = D("0.04")
    step_pct: Decimal = D("0.05")
    round_to: Decimal = D("10")
    min_transfer: Decimal = D("100")
    floor_pct: Decimal = D("0.5")
    cap_pct: Decimal = D("0.5")
    reserve_floor_pct: Decimal = D("0.1")
    min_proposals: int = 3
    version: str = "C1"

    def __post_init__(self) -> None:
        if self.review_every < 1 or self.min_history < 2 or self.lookback < self.min_history:
            raise ValueError("review_every >= 1, min_history >= 2 and lookback >= min_history are required")
        if not (D("0") < self.step_pct <= D("0.25")) or self.min_transfer <= 0 or self.round_to <= 0:
            raise ValueError("step_pct must be in (0, 0.25] and amounts must be positive")

    def describe(self) -> dict[str, str]:
        return {"version": self.version, "review_every": str(self.review_every), "min_history": str(self.min_history),
                "lookback": str(self.lookback), "drawdown_weight": str(self.drawdown_weight), "margin": str(self.margin),
                "flip_margin": str(self.flip_margin), "step_pct": str(self.step_pct), "round_to": str(self.round_to),
                "min_transfer": str(self.min_transfer), "floor_pct": str(self.floor_pct), "cap_pct": str(self.cap_pct),
                "reserve_floor_pct": str(self.reserve_floor_pct), "min_proposals": str(self.min_proposals)}

    def is_review_session(self, marked_sessions: int) -> bool:
        """``marked_sessions`` counts the session being closed. First review once history suffices, then periodically."""
        return marked_sessions >= self.min_history and (marked_sessions - self.min_history) % self.review_every == 0


@dataclass(frozen=True)
class PodEvidence:
    """Everything Apex looked at for one pod. All of it is known at the close of the review session."""
    pod_id: str
    history: int
    window: int
    window_return: Decimal
    window_drawdown: Decimal  # <= 0
    score: Decimal
    lifetime_return: Decimal
    proposals: int
    funded_proposals: int
    closed_trades: int
    win_rate: Decimal | None
    sleeve_nav: Decimal
    sleeve_cash: Decimal
    committed: Decimal
    net_capital: Decimal  # all transfers so far, including the initial funding
    initial_funding: Decimal

    @property
    def free_cash(self) -> Decimal:
        return max(self.sleeve_cash - self.committed, D("0"))

    @property
    def utilization(self) -> Decimal:
        return ((self.sleeve_nav - self.sleeve_cash) / self.sleeve_nav) if self.sleeve_nav > 0 else D("0")

    def as_payload(self) -> dict[str, Any]:
        q = lambda x: format(x.quantize(RATIO), "f")  # noqa: E731
        m = lambda x: format(x.quantize(CENT), "f")  # noqa: E731
        return {"history_sessions": self.history, "window_sessions": self.window, "window_return": q(self.window_return),
                "window_max_drawdown": q(self.window_drawdown), "score": q(self.score), "lifetime_return": q(self.lifetime_return),
                "proposals": self.proposals, "funded_proposals": self.funded_proposals, "closed_trades": self.closed_trades,
                "win_rate": None if self.win_rate is None else q(self.win_rate), "sleeve_nav": m(self.sleeve_nav),
                "sleeve_cash": m(self.sleeve_cash), "committed_cash": m(self.committed), "free_cash": m(self.free_cash),
                "utilization": q(self.utilization), "net_capital": m(self.net_capital), "initial_funding": m(self.initial_funding)}


@dataclass(frozen=True)
class Transfer:
    sleeve_id: str
    amount: Decimal  # signed: > 0 into the sleeve, < 0 reclaimed from it
    source: str  # where a grant came from / where a reclaim goes: a pod id or "reserve"


@dataclass(frozen=True)
class CapitalOutcome:
    outcome: str  # REALLOCATED | HELD
    reasons: tuple[str, ...]
    rationale: str
    transfers: tuple[Transfer, ...] = ()
    leader: str | None = None
    trailer: str | None = None
    gap: Decimal | None = None

    def ordered(self) -> list[Transfer]:
        """Reclaims first, so the cash is in the reserve before it is granted."""
        return sorted(self.transfers, key=lambda t: (t.amount >= 0, t.sleeve_id))


REASON_TEXT = {
    "UNTRUSTED_DATA": "A holding could not be marked at the close, so the books are untrusted. Apex moves no capital on untrusted data.",
    "INSUFFICIENT_HISTORY": "Fewer than two pods have enough marked sessions to be judged, so nothing is decided.",
    "DRAW": "The gap between the two scores is inside the margin, so the competition is too close to call.",
    "NO_WINNER": "Even the better pod has not made money after its drawdown, so no one is rewarded for being least bad.",
    "LEADER_CANNOT_DEPLOY": "The leading pod made too few proposals in the window to show it could put more capital to work.",
    "NO_FREE_CAPITAL": "No uncommitted cash can be moved: the trailing pod is at its floor or fully committed, and the reserve is at its floor or the leader is at its cap.",
    "REALLOCATED": "Apex moved one step of capital toward the pod whose evidence is stronger.",
}


def _floor(x: Decimal, unit: Decimal) -> Decimal:
    return (x / unit).to_integral_value(rounding=ROUND_FLOOR) * unit


def pct(x: Decimal) -> str:
    return f"{(x * 100).quantize(D('0.1'))}%"


def decide(policy: CapitalPolicy, evidence: Mapping[str, PodEvidence], *, fund_nav: Decimal, reserve: Decimal,
           trusted: bool, previous_beneficiary: str | None) -> CapitalOutcome:
    """Pure: the same evidence always gives the same decision."""
    if not trusted:
        return CapitalOutcome("HELD", ("UNTRUSTED_DATA",), REASON_TEXT["UNTRUSTED_DATA"])
    judged = sorted((e for e in evidence.values() if e.history >= policy.min_history), key=lambda e: (-e.score, e.pod_id))
    if len(judged) < 2:
        return CapitalOutcome("HELD", ("INSUFFICIENT_HISTORY",), REASON_TEXT["INSUFFICIENT_HISTORY"])
    lead, trail = judged[0], judged[-1]
    gap = lead.score - trail.score
    need = policy.flip_margin if previous_beneficiary not in (None, lead.pod_id) else policy.margin

    def held(code: str, text: str) -> CapitalOutcome:
        return CapitalOutcome("HELD", (code,), text, (), lead.pod_id, trail.pod_id, gap)

    L, T = lead.pod_id.capitalize(), trail.pod_id.capitalize()
    summary = f"{L} scored {pct(lead.score)} and {T} {pct(trail.score)} (gap {pct(gap)})"
    if gap < need:
        return held("DRAW", f"{summary}; the gap is under the {pct(need)} needed to act. {REASON_TEXT['DRAW']}")
    if lead.score <= 0:
        return held("NO_WINNER", f"{summary}. {REASON_TEXT['NO_WINNER']}")
    if lead.proposals < policy.min_proposals:
        return held("LEADER_CANNOT_DEPLOY", f"{summary}; {L} made {lead.proposals} proposals "
                    f"in the window, under the {policy.min_proposals} required. {REASON_TEXT['LEADER_CANNOT_DEPLOY']}")
    step = _floor(fund_nav * policy.step_pct, policy.round_to)
    reclaimable = max(min(trail.free_cash, trail.sleeve_nav - policy.floor_pct * trail.initial_funding), D("0"))
    reserve_room = max(reserve - policy.reserve_floor_pct * fund_nav, D("0"))
    cap_room = max(policy.cap_pct * fund_nav - lead.sleeve_nav, D("0"))
    grant = _floor(min(step, cap_room, reclaimable + reserve_room), CENT)
    if grant < policy.min_transfer:
        return held("NO_FREE_CAPITAL", f"{summary}, but only ${grant} could move (minimum ${policy.min_transfer}). {REASON_TEXT['NO_FREE_CAPITAL']}")
    reclaim = _floor(min(reclaimable, grant), CENT)
    from_reserve = grant - reclaim
    transfers = [Transfer(lead.pod_id, grant, trail.pod_id if reclaim else "reserve")]
    if reclaim:
        transfers.append(Transfer(trail.pod_id, -reclaim, lead.pod_id))
    parts = []
    if reclaim:
        parts.append(f"${reclaim} reclaimed from {T}'s uncommitted cash")
    if from_reserve:
        parts.append(f"${from_reserve} granted from the central reserve")
    rationale = (f"{summary}. {L} receives ${grant}: " + " and ".join(parts) + ". No position was sold and no queued order was touched.")
    return CapitalOutcome("REALLOCATED", ("REALLOCATED",), rationale, tuple(transfers), lead.pod_id, trail.pod_id, gap)


# --- evidence from the ledger -------------------------------------------------------------------------

def build_evidence(policy: CapitalPolicy, events: Sequence[LedgerEvent], ep: EpochState, pod_ids: Sequence[str]) -> dict[str, PodEvidence]:
    """Evidence as of now: only ledger events already appended. ``ep`` is the state after those events."""
    out: dict[str, PodEvidence] = {}
    marks_days = sorted(ep.marks)
    window_days = set(marks_days[-policy.lookback:])
    first_window_day = min(window_days) if window_days else ""
    for pid in pod_ids:
        pts: list[FlowPoint] = flow_adjusted_series(events, ep.epoch_id, pid)
        ret, dd, n = window_performance(pts, policy.lookback)
        proposals = [e for e in events if e.draft.kind is EventKind.PROPOSAL_SUBMITTED and e.draft.epoch_id == ep.epoch_id
                     and e.draft.payload["pod_id"] == pid and str(e.draft.payload["as_of_session"]) >= first_window_day]
        pids = {str(e.draft.payload["proposal_id"]) for e in proposals}
        funded = sum(1 for e in events if e.draft.kind is EventKind.APEX_DECISION and e.draft.epoch_id == ep.epoch_id
                     and e.draft.payload["proposal_id"] in pids and e.draft.payload["outcome"] == "FUNDED")
        trips = [t for t in round_trips(events, ep.epoch_id, pid) if t.exit_day >= first_window_day]
        sl = ep.sleeves[pid]
        nav = pts[-1].nav if pts else sl.cash
        net = sum((D(str(e.draft.payload["amount"])) for e in events if e.draft.kind is EventKind.SLEEVE_FUNDED
                   and e.draft.epoch_id == ep.epoch_id and e.draft.payload["sleeve_id"] == pid), D("0"))
        initial = next((D(str(e.draft.payload["amount"])) for e in events if e.draft.kind is EventKind.SLEEVE_FUNDED
                        and e.draft.epoch_id == ep.epoch_id and e.draft.payload["sleeve_id"] == pid), D("0"))
        out[pid] = PodEvidence(
            pid, len(pts), n, ret, dd, ret + policy.drawdown_weight * dd, (pts[-1].index - 1) if pts else D("0"),
            len(proposals), funded, len(trips), (D(sum(1 for t in trips if t.pnl > 0)) / len(trips)) if trips else None,
            nav, sl.cash, ep.committed_cash(pid), net, initial)
    return out


def previous_beneficiary(events: Sequence[LedgerEvent], epoch_id: str) -> str | None:
    for e in reversed(events):
        if e.draft.kind is EventKind.APEX_CAPITAL_DECISION and e.draft.epoch_id == epoch_id and e.draft.payload["outcome"] == "REALLOCATED":
            grants = [t for t in e.draft.payload["transfers"] if D(str(t["amount"])) > 0]
            return str(grants[0]["sleeve_id"]) if grants else None
    return None


def verify_capital(events: Sequence[LedgerEvent], epoch_id: str) -> list[str]:
    """Re-check every capital review against the ledger alone. Returns problems (empty = all transfers verified).

    For each decision: the transfers add up to the change in the reserve, the reserve it started from is what the
    SLEEVE_FUNDED history says it was, every transfer exists as a SLEEVE_FUNDED event carrying the review id (and nothing
    else does) after the decision, a reclaim never exceeds the uncommitted cash the evidence recorded, and the fund NAV it
    quoted is the verified mark of that session."""
    problems: list[str] = []
    initial = D("0")
    funded_so_far = D("0")
    nav_by_day: dict[str, Decimal] = {}
    decisions: dict[str, tuple[int, Mapping[str, Any], Decimal]] = {}
    fundings: dict[str, list[tuple[int, str, Decimal]]] = {}
    for e in events:
        d = e.draft
        if d.epoch_id != epoch_id:
            continue
        if d.kind is EventKind.EPOCH_OPENED:
            initial = D(str(d.payload["initial_cash"]))
        elif d.kind is EventKind.SESSION_MARKED:
            nav_by_day[str(d.payload["session_day"])] = D(str(d.payload["nav"]))
        elif d.kind is EventKind.APEX_CAPITAL_DECISION:
            decisions[str(d.payload["review_id"])] = (e.seq, d.payload, initial - funded_so_far)
        elif d.kind is EventKind.SLEEVE_FUNDED:
            amount = D(str(d.payload["amount"]))
            funded_so_far += amount
            fundings.setdefault(str(d.payload["ref"]), []).append((e.seq, str(d.payload["sleeve_id"]), amount))
    for rid, (seq, p, reserve_now) in decisions.items():
        moves = [(str(t["sleeve_id"]), D(str(t["amount"]))) for t in p["transfers"]]
        draw = sum((a for _, a in moves), D("0"))
        if D(str(p["reserve_before"])) != reserve_now:
            problems.append(f"{rid}: reserve_before {p['reserve_before']} != {reserve_now} from the funding history")
        if D(str(p["reserve_after"])) != D(str(p["reserve_before"])) - draw:
            problems.append(f"{rid}: transfers do not add up to the change in the reserve")
        got = sorted((sid, a) for _, sid, a in fundings.get(rid, []))
        if got != sorted(moves):
            problems.append(f"{rid}: SLEEVE_FUNDED events {got} do not match the decision's transfers {sorted(moves)}")
        if any(s < seq for s, _, _ in fundings.get(rid, [])):
            problems.append(f"{rid}: a transfer precedes its decision")
        if p["outcome"] == "HELD" and moves:
            problems.append(f"{rid}: a HELD review moved capital")
        if len([1 for _, a in moves if a > 0]) > 1:
            problems.append(f"{rid}: more than one grant")
        for sid, a in moves:
            if a < 0 and -a > D(str(p["evidence"][sid]["free_cash"])):
                problems.append(f"{rid}: reclaimed {-a} from {sid} but only {p['evidence'][sid]['free_cash']} was uncommitted")
        if nav_by_day.get(str(p["session_day"])) != D(str(p["fund_nav"])):
            problems.append(f"{rid}: quoted fund NAV is not the verified mark of {p['session_day']}")
    stray = set(fundings) - set(decisions) - {"d0-initial"}
    if stray:
        problems.append(f"funding events without a capital decision: {sorted(stray)}")
    return problems
