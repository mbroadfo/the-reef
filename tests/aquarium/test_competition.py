"""The two-pod competition: registry, proposal contract, Apex decisions, sleeve independence, snapshot."""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from tests.fixtures.competition_scenario import FIRST, SESSIONS, make_comp_deps, make_comp_world
from tests.hunter.test_engine_safety import Crash, CrashingStore
from the_reef.engine.advance import advance, bootstrap, next_session_to_advance
from the_reef.ledger.events import EventKind
from the_reef.ledger.ledger import InMemoryEventStore, Ledger
from the_reef.pods.registry import POD_REGISTRY, PodStatus
from tools.build_competition_snapshot import DEFAULT_OUT, build, render

D = Decimal
REQUIRED = {"proposal_id", "pod_id", "symbol", "thesis", "findings", "created_at", "as_of_session", "entry_plan", "exit_plan",
            "risk", "capital_request", "strategy"}


@pytest.fixture(scope="module")
def world():
    return make_comp_world()


@pytest.fixture(scope="module")
def run(world):
    deps = make_comp_deps(world)
    led = Ledger()
    bootstrap(led, deps, world.calendar.session(world.days[FIRST]).open - timedelta(hours=1))
    for i in range(FIRST, FIRST + SESSIONS):
        advance(led, deps, world.days[i])
    return deps, led


@pytest.fixture(scope="module")
def snap():
    return build()


def kinds(led, kind):
    return [e.draft.payload for e in led.store.read_all() if e.draft.kind is kind]


# --- registry -------------------------------------------------------------------------------------

def test_six_pods_two_active_and_inactive_ones_are_honest():
    assert len(POD_REGISTRY) == 6 and len({p.pod_id for p in POD_REGISTRY}) == 6
    active = [p for p in POD_REGISTRY if p.status is PodStatus.ACTIVE]
    assert [p.pod_id for p in active] == ["momentum", "contrarian"]
    for p in POD_REGISTRY:
        assert p.mandate and p.research_agents == p.research_agents
        if p.status is PodStatus.INACTIVE:
            assert p.sleeve_weight == 0 and p.make_strategy is None and p.inactive_reason
        else:
            assert p.sleeve_weight > 0 and p.make_strategy is not None and len(p.research_agents) >= 3


def test_inactive_pods_get_no_sleeve_and_no_activity(run):
    deps, led = run
    assert set(led.state.epoch().sleeves) == {"momentum", "contrarian"}
    assert {e["sleeve_id"] for e in kinds(led, EventKind.PROPOSAL_SUBMITTED)} <= {"momentum", "contrarian"}


# --- proposals and Apex decisions ----------------------------------------------------------------

def test_two_pods_submit_different_proposals_with_the_full_contract(run):
    _, led = run
    packets = kinds(led, EventKind.PROPOSAL_SUBMITTED)
    by_pod = {}
    for p in packets:
        assert REQUIRED <= set(p), f"missing {REQUIRED - set(p)}"
        assert p["findings"] and p["thesis"] and p["exit_plan"]["rules"]
        assert D(p["exit_plan"]["stop_price"]) < D(p["entry_plan"]["reference_price"])
        by_pod.setdefault(p["pod_id"], []).append(p)
    assert set(by_pod) == {"momentum", "contrarian"}
    assert {p["strategy"].split("@")[0] for p in packets} == {"hunter-momentum", "contrarian-reversion"}
    assert len({p["thesis"] for p in by_pod["momentum"]} & {p["thesis"] for p in by_pod["contrarian"]}) == 0
    assert {p["symbol"] for p in by_pod["momentum"]} != {p["symbol"] for p in by_pod["contrarian"]}


def test_every_proposal_gets_exactly_one_apex_decision_with_reasons(run):
    _, led = run
    ids = [p["proposal_id"] for p in kinds(led, EventKind.PROPOSAL_SUBMITTED)]
    decisions = {d["proposal_id"]: d for d in kinds(led, EventKind.APEX_DECISION)}
    assert sorted(ids) == sorted(decisions) and len(set(ids)) == len(ids)
    outcomes = {d["outcome"] for d in decisions.values()}
    assert outcomes == {"FUNDED", "DECLINED"}
    for d in decisions.values():
        if d["outcome"] == "DECLINED":
            assert d["reasons"], "a decline always says why"
        else:
            assert d["order_id"] and not d["reasons"]
            assert d["granted_shares"] <= d["requested_shares"] and d["granted_shares"] <= d["ceiling_shares"]
    assert any("D0_RANK_CAP" in d["reasons"] for d in decisions.values())
    assert any("PENDING_CASH_DEAL" in d["reasons"] for d in decisions.values())


def test_a_funded_decision_is_backed_by_a_queued_order_and_a_declined_one_by_none(run):
    _, led = run
    queued = {(o["sleeve_id"], o["order_id"]) for o in kinds(led, EventKind.ORDER_QUEUED)}
    for d in kinds(led, EventKind.APEX_DECISION):
        if d["outcome"] == "FUNDED":
            assert (d["sleeve_id"], d["order_id"]) in queued
        elif "D0_RANK_CAP" in d["reasons"]:
            assert not any(q[1].endswith(f":{d['proposal_id'].split(':')[2]}:open") and q[0] == d["sleeve_id"]
                           and d["proposal_id"].split(":")[1] in q[1] for q in queued)


# --- independent sleeve accounting ---------------------------------------------------------------

def test_sleeves_are_independent_and_reconcile_to_the_fund(run, snap):
    deps, led = run
    ep = led.state.epoch()
    sleeves = ep.sleeves
    assert all(s.cash >= 0 for s in sleeves.values())
    nav = {p["pod_id"]: D(p["nav"]) for p in snap["pods"] if p["status"] == "ACTIVE"}
    assert sum(nav.values(), D("0")) + ep.unallocated == D(snap["fund"]["nav"])
    for p in snap["pods"]:
        if p["status"] == "ACTIVE":
            assert D(p["funded"]) + D(p["realized_pnl"]) + D(p["unrealized_pnl"]) == D(p["nav"])
    # A pod's fills only ever touch its own sleeve.
    for e in led.store.read_all():
        if e.draft.kind is EventKind.FILL:
            assert e.draft.payload["sleeve_id"] in nav


def test_both_pods_trade_and_the_ranking_uses_risk_adjusted_figures(snap):
    active = [p for p in snap["pods"] if p["status"] == "ACTIVE"]
    assert all(p["trades"] > 0 and p["rank"] in (1, 2) for p in active)
    assert sorted(p["rank"] for p in active) == [1, 2]
    best = min(active, key=lambda p: p["rank"])
    assert best["sharpe_like"] >= max(p["sharpe_like"] for p in active)
    for p in snap["pods"]:
        if p["status"] == "INACTIVE":
            assert "nav" not in p and "return" not in p and "trades" not in p


# --- recovery -------------------------------------------------------------------------------------

def test_crash_recovery_reproduces_the_competition_ledger(world, run):
    _, expected = run
    total = len(expected.store.read_all())
    for crash_at in range(2, total, 23):
        store = CrashingStore(crash_at)
        deps = make_comp_deps(world)
        led = Ledger(store)
        with pytest.raises(Crash):
            bootstrap(led, deps, world.calendar.session(world.days[FIRST]).open - timedelta(hours=1))
            for i in range(FIRST, FIRST + SESSIONS):
                advance(led, deps, world.days[i])
        revived = Ledger(InMemoryEventStore(store.read_all()))
        bootstrap(revived, deps, world.calendar.session(world.days[FIRST]).open - timedelta(hours=1))
        first = world.days.index(next_session_to_advance(revived, deps, world.days[FIRST]))
        for i in range(first, FIRST + SESSIONS):
            advance(revived, deps, world.days[i])
        assert revived.state.head_hash == expected.state.head_hash, f"diverged after a crash at append {crash_at}"


# --- the engine -> aquarium contract -------------------------------------------------------------

def test_snapshot_is_deterministic_and_the_committed_file_is_current(snap):
    assert render(build()) == render(snap)
    assert json.loads(Path(DEFAULT_OUT).read_text(encoding="utf-8")) == json.loads(render(snap)), \
        "dashboard/frontend/public/reef2/snapshot.json is stale: run tools/build_competition_snapshot.py"


def test_snapshot_checks_pass_and_every_story_is_traceable(snap):
    assert all(c["ok"] for c in snap["checks"])
    seqs = {e["seq"] for e in snap["events"]}
    for r in snap["proposals"]:
        assert r["packet_seq"] in seqs and r["decision"]["seq"] in seqs
        lc = r.get("lifecycle") or {}
        if lc.get("entry"):
            assert lc["entry"]["seq"] in seqs
        if lc.get("exit"):
            assert lc["exit"]["seq"] in seqs
        if r["decision"]["outcome"] == "DECLINED":
            assert "lifecycle" not in r, "a declined proposal has no trade"
    closed = [r for r in snap["proposals"] if (r.get("lifecycle") or {}).get("status") == "CLOSED"]
    assert closed and all(r["lifecycle"]["pnl"] is not None and r["lifecycle"]["sleeve_nav_after"] for r in closed)
