"""Apex capital competition: the policy, the accounting around transfers, and the demonstration run."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from tests.fixtures.competition_scenario import FIRST, SESSIONS, make_comp_deps, make_comp_world
from tests.hunter.test_engine_safety import Crash, CrashingStore
from the_reef.allocation.capital import (
    CapitalPolicy, PodEvidence, build_evidence, decide, previous_beneficiary, verify_capital,
)
from the_reef.engine.advance import advance, bootstrap, next_session_to_advance
from the_reef.ledger import events as ev
from the_reef.ledger.events import EventKind, LedgerEvent
from the_reef.ledger.ledger import InMemoryEventStore, Ledger
from the_reef.ledger.state import LedgerError, LedgerState, apply, check_invariants, valuation
from the_reef.performance.metrics import FlowPoint, flow_adjusted_series, window_performance

D = Decimal
P = CapitalPolicy()


def evidence(pod: str, *, ret: str = "0", dd: str = "0", history: int = 30, proposals: int = 5, nav: str = "3000",
             cash: str = "2000", committed: str = "0", initial: str = "3000", net: str = "3000") -> PodEvidence:
    r, d = D(ret), D(dd)
    return PodEvidence(pod, history, min(history, P.lookback), r, d, r + P.drawdown_weight * d, r, proposals, 2, 1, None,
                       D(nav), D(cash), D(committed), D(net), D(initial))


def run_decide(a: PodEvidence, b: PodEvidence, *, fund_nav="10000", reserve="4000", trusted=True, prev=None):
    return decide(P, {a.pod_id: a, b.pod_id: b}, fund_nav=D(fund_nav), reserve=D(reserve), trusted=trusted, previous_beneficiary=prev)


# --- the policy on hand-built evidence -------------------------------------------------------------

def test_a_winning_team_is_paid_from_a_losing_teams_idle_cash():
    out = run_decide(evidence("momentum", ret="0.08"), evidence("contrarian", ret="-0.03", dd="-0.04"))
    assert out.outcome == "REALLOCATED" and out.leader == "momentum" and out.trailer == "contrarian"
    by = {t.sleeve_id: t.amount for t in out.transfers}
    assert by == {"momentum": D("500.00"), "contrarian": D("-500.00")}  # 5% of $10,000, all from the trailer
    assert out.ordered()[0].amount < 0, "the reclaim is ordered before the grant"
    assert "Momentum" in out.rationale and "reclaimed" in out.rationale


def test_the_loser_cannot_be_drained_below_its_floor_and_the_reserve_tops_up_the_rest():
    # contrarian holds $1,600 of a $1,700 sleeve; its floor is 50% of $3,000 = $1,500, so only $200 can be reclaimed.
    out = run_decide(evidence("momentum", ret="0.08"), evidence("contrarian", ret="-0.03", nav="1700", cash="1600"))
    by = {t.sleeve_id: t.amount for t in out.transfers}
    assert by["contrarian"] == D("-200.00") and by["momentum"] == D("500.00")
    assert "granted from the central reserve" in out.rationale


def test_both_teams_performing_poorly_means_no_one_is_rewarded():
    out = run_decide(evidence("momentum", ret="-0.01", dd="-0.02"), evidence("contrarian", ret="-0.08", dd="-0.05"))
    assert out.outcome == "HELD" and out.reasons == ("NO_WINNER",) and not out.transfers


def test_a_close_race_is_a_draw_and_reversing_the_last_transfer_needs_a_bigger_gap():
    close = run_decide(evidence("momentum", ret="0.03"), evidence("contrarian", ret="0.02"))
    assert close.outcome == "HELD" and close.reasons == ("DRAW",)
    # contrarian leads by 3 points: enough on its own, but not enough to undo a transfer that went to momentum
    flip = run_decide(evidence("momentum", ret="0.01"), evidence("contrarian", ret="0.04"), prev="momentum")
    assert flip.outcome == "HELD" and flip.reasons == ("DRAW",)
    same = run_decide(evidence("momentum", ret="0.01"), evidence("contrarian", ret="0.04"), prev="contrarian")
    assert same.outcome == "REALLOCATED" and same.leader == "contrarian"
    wide = run_decide(evidence("momentum", ret="0.00"), evidence("contrarian", ret="0.05"), prev="momentum")
    assert wide.outcome == "REALLOCATED" and wide.leader == "contrarian"


def test_a_pod_without_enough_history_is_not_judged():
    out = run_decide(evidence("momentum", ret="0.2", history=P.min_history - 1), evidence("contrarian", ret="-0.1"))
    assert out.outcome == "HELD" and out.reasons == ("INSUFFICIENT_HISTORY",)
    out = run_decide(evidence("momentum", ret="0.2", history=3), evidence("contrarian", ret="-0.1", history=3))
    assert out.reasons == ("INSUFFICIENT_HISTORY",)


def test_untrusted_data_moves_nothing_however_good_the_numbers_look():
    out = run_decide(evidence("momentum", ret="0.3"), evidence("contrarian", ret="-0.3"), trusted=False)
    assert out.outcome == "HELD" and out.reasons == ("UNTRUSTED_DATA",) and not out.transfers


def test_insufficient_free_cash_moves_nothing():
    # the trailer is at its floor and fully committed; the reserve is at its floor; so there is nothing movable
    out = run_decide(evidence("momentum", ret="0.08"), evidence("contrarian", ret="-0.03", nav="1500", cash="1500", committed="1500"),
                     reserve="1000")
    assert out.outcome == "HELD" and out.reasons == ("NO_FREE_CAPITAL",)
    # cash promised to queued orders is never counted as free
    assert evidence("contrarian", cash="1000", committed="900").free_cash == D("100")


def test_a_leader_that_cannot_show_it_uses_capital_is_not_funded():
    out = run_decide(evidence("momentum", ret="0.08", proposals=1), evidence("contrarian", ret="-0.03"))
    assert out.outcome == "HELD" and out.reasons == ("LEADER_CANNOT_DEPLOY",)


def test_the_leader_never_exceeds_the_cap_and_the_reserve_never_drops_below_its_floor():
    big = evidence("momentum", ret="0.08", nav="4900")  # cap is 50% of $10,000 = $5,000, so $100 of room
    out = run_decide(big, evidence("contrarian", ret="-0.03"))
    assert {t.sleeve_id: t.amount for t in out.transfers}["momentum"] == D("100.00")
    out = run_decide(evidence("momentum", ret="0.08"), evidence("contrarian", ret="-0.03", nav="1500", cash="1500"), reserve="1100")
    by = {t.sleeve_id: t.amount for t in out.transfers}
    assert by == {"momentum": D("100.00")}, "only the $100 above the reserve floor moves, and the trailer sits at its floor"


def test_the_decision_is_deterministic_and_conserves_money():
    a, b = evidence("momentum", ret="0.08"), evidence("contrarian", ret="-0.03", dd="-0.01")
    first, second = run_decide(a, b), run_decide(b, a)
    assert first == second  # the order evidence arrives in does not matter
    reserve_draw = sum((t.amount for t in first.transfers), D("0"))
    assert reserve_draw >= 0 and reserve_draw <= D("4000")


def test_policy_rejects_nonsense():
    with pytest.raises(ValueError):
        CapitalPolicy(review_every=0)
    with pytest.raises(ValueError):
        CapitalPolicy(min_history=30, lookback=20)
    with pytest.raises(ValueError):
        CapitalPolicy(step_pct=D("0.5"))
    assert [n for n in range(1, 40) if P.is_review_session(n)] == [15, 25, 35]


# --- capital-flow-adjusted performance ---------------------------------------------------------------

def test_receiving_capital_is_not_a_return():
    pts = [FlowPoint("d1", D("3030"), D("3000"), D("3000"), D("0.01"), D("1.01")),
           # $500 arrives after d1; the sleeve then earns exactly 1% on $3,530
           FlowPoint("d2", D("3565.3"), D("3530"), D("500"), D("0.01"), D("1.0201"))]
    ret, dd, n = window_performance(pts, 20)
    assert (ret.quantize(D("0.0001")), dd, n) == (D("0.0201"), D("0"), 2)
    naive = D("3565.3") / D("3000") - 1
    assert naive > D("0.18"), "a naive return would credit the sleeve with the transfer"


# --- the demonstration run ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def world():
    return make_comp_world()


def play(world, sessions=SESSIONS, capital=P):
    deps = make_comp_deps(world, capital=capital)
    led = Ledger()
    bootstrap(led, deps, world.calendar.session(world.days[FIRST]).open - timedelta(hours=1))
    for i in range(FIRST, FIRST + sessions):
        advance(led, deps, world.days[i])
    return deps, led


@pytest.fixture(scope="module")
def run(world):
    return play(world)


def states(led: Ledger) -> list[tuple[LedgerEvent, LedgerState]]:
    st, out = LedgerState(), []
    for e in led.store.read_all():
        st = apply(st, e)
        out.append((e, st))
    return out


def decisions(led: Ledger):
    return [e for e in led.store.read_all() if e.draft.kind is EventKind.APEX_CAPITAL_DECISION]


def test_the_initial_allocation_is_preserved_until_the_first_review(run):
    _, led = run
    funding = [e for e in led.store.read_all() if e.draft.kind is EventKind.SLEEVE_FUNDED]
    assert [(e.draft.payload["sleeve_id"], e.draft.payload["amount"], e.draft.payload["ref"]) for e in funding[:2]] == [
        ("momentum", "3000.00", "d0-initial"), ("contrarian", "3000.00", "d0-initial")]
    first = decisions(led)[0]
    marks_before = sum(1 for e, _ in states(led) if e.seq < first.seq and e.draft.kind is EventKind.SESSION_MARKED)
    assert marks_before == P.min_history
    assert all(e.seq > first.seq for e in funding[2:])


def test_both_sharks_compete_and_apex_makes_a_meaningful_reallocation(run):
    _, led = run
    ds = decisions(led)
    assert [d.draft.payload["review_no"] for d in ds] == [15, 25, 35, 45, 55, 65]
    moved = [d for d in ds if d.draft.payload["outcome"] == "REALLOCATED"]
    assert len(moved) >= 1 and any(d.draft.payload["outcome"] == "HELD" for d in ds)
    first = moved[0].draft.payload
    assert first["leader"] == "momentum" and first["trailer"] == "contrarian"
    ev_m, ev_c = first["evidence"]["momentum"], first["evidence"]["contrarian"]
    assert D(ev_m["score"]) > D(ev_c["score"]) and ev_m["proposals"] >= 3 and ev_c["proposals"] >= 1
    assert {t["sleeve_id"] for t in first["transfers"]} == {"momentum", "contrarian"}
    # the chain: the decision is followed by the signed funding events it ordered, and the sleeves hold the result
    final = led.state.epoch().sleeves
    net = {sid: sum(D(str(e.draft.payload["amount"])) for e in led.store.read_all()
                    if e.draft.kind is EventKind.SLEEVE_FUNDED and e.draft.payload["sleeve_id"] == sid) for sid in final}
    assert net["momentum"] > D("3000") and net["contrarian"] < D("3000")


def test_every_decision_carries_evidence_rationale_time_and_the_resulting_transfers(run):
    _, led = run
    for d in decisions(led):
        p = d.draft.payload
        assert p["rationale"] and p["reasons"] and p["policy"]["version"] == "C1" and p["decided_at"]
        assert set(p["evidence"]) == {"momentum", "contrarian"}
        assert {"window_return", "window_max_drawdown", "score", "proposals", "free_cash", "committed_cash"} <= set(p["evidence"]["momentum"])
        assert (p["outcome"] == "REALLOCATED") == bool(p["transfers"])


def test_transfers_verify_against_the_ledger_and_tampering_is_detected(run):
    _, led = run
    events = led.store.read_all()
    assert verify_capital(events, events[0].draft.epoch_id) == []
    eid = events[0].draft.epoch_id
    # drop one SLEEVE_FUNDED transfer
    victim = next(e for e in events if e.draft.kind is EventKind.SLEEVE_FUNDED and e.draft.payload["ref"].startswith("review-"))
    assert verify_capital([e for e in events if e is not victim], eid)
    # change a transfer amount
    forged = replace(victim.draft, payload={**victim.draft.payload, "amount": "999.00"})
    assert verify_capital([LedgerEvent(e.seq, e.prev_hash, e.hash, forged) if e is victim else e for e in events], eid)
    # a funding event nobody decided
    stray = replace(victim.draft, payload={**victim.draft.payload, "ref": "review-999"})
    assert verify_capital([LedgerEvent(e.seq, e.prev_hash, e.hash, stray) if e is victim else e for e in events], eid)


def test_no_money_is_created_or_destroyed_and_nav_is_unchanged_by_transfers(run):
    _, led = run
    st_prev = None
    checked = 0
    for e, st in states(led):
        check_invariants(st)
        ep = st.epoch()
        assert ep.unallocated >= 0 and all(s.cash >= 0 for s in ep.sleeves.values())
        assert ep.cash + sum((p.cost for s in ep.sleeves.values() for p in s.positions.values()), D("0")) == ep.initial_cash + ep.realized_pnl
        if e.draft.kind is EventKind.SLEEVE_FUNDED and e.draft.payload["ref"] != "d0-initial" and st_prev is not None:
            before, after = st_prev.epoch(), ep
            nav = lambda x: valuation(x, x.last_mark_prices, x.last_unmarked)[0]  # noqa: E731
            assert nav(before) == nav(after), "a transfer moved the fund NAV"
            assert {k: s.realized_pnl for k, s in before.sleeves.items()} == {k: s.realized_pnl for k, s in after.sleeves.items()}, \
                "a transfer rewrote realized P&L"
            assert {k: s.positions for k, s in before.sleeves.items()} == {k: s.positions for k, s in after.sleeves.items()}, \
                "a transfer liquidated a position"
            checked += 1
        st_prev = st
    assert checked >= 2


def test_flow_adjusted_returns_do_not_credit_a_sleeve_for_a_grant(run):
    _, led = run
    events = led.store.read_all()
    eid = events[0].draft.epoch_id
    pts = flow_adjusted_series(events, eid, "momentum")
    granted = [p for p in pts if p.flow > 0 and p.day != pts[0].day]
    assert granted, "momentum received capital during the run"
    for p in granted:
        assert p.base == [q for q in pts if q.day < p.day][-1].nav + p.flow
        assert p.ret == p.nav / p.base - 1
        assert abs(p.ret) < D("0.05"), "a $500 grant must not show up as a ~16% return"
    # the chained index reproduces the sleeve's final time-weighted return
    prod = D("1")
    for p in pts:
        prod *= 1 + p.ret
    assert abs(prod - pts[-1].index) < D("0.000001")


def test_a_review_uses_only_what_existed_at_its_close(world, run):
    """Truncating the world after review 25 leaves reviews 15 and 25 byte-identical."""
    _, full = run
    _, short = play(world, sessions=26)
    f = {d.draft.payload["review_no"]: d for d in decisions(full)}
    s = {d.draft.payload["review_no"]: d for d in decisions(short)}
    assert sorted(s) == [15, 25]
    for n in s:
        assert s[n].draft.fingerprint == f[n].draft.fingerprint and s[n].hash == f[n].hash


def test_a_replayed_session_appends_nothing_and_the_ledger_reconciles(world, run):
    deps, led = run
    head = led.state.head_hash
    again = advance(led, deps, world.days[FIRST + SESSIONS - 1])
    assert again.appended == 0 and led.state.head_hash == head
    replayed = Ledger(InMemoryEventStore(led.store.read_all()))
    assert replayed.state.digest() == led.state.digest()


def test_crash_recovery_around_every_capital_event_reproduces_the_ledger(world, run):
    deps0, expected = run
    events = expected.store.read_all()
    # crash before, between and after the decision event and each of its transfers, for the first two reviews
    targets = []
    for d in decisions(expected)[:2]:
        targets += range(d.seq - 2, d.seq + 5)
    for crash_at in targets:
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
        assert verify_capital(revived.store.read_all(), events[0].draft.epoch_id) == []


# --- ledger guard rails ---------------------------------------------------------------------------

def test_cash_committed_to_a_queued_order_cannot_be_swept(world, run):
    deps, _ = run
    led = Ledger()
    t0 = world.calendar.session(world.days[FIRST]).open - timedelta(hours=1)
    bootstrap(led, deps, t0)
    eid = deps.epoch_id
    led.append(ev.order_queued(eid, t0, sleeve_id="momentum", order_id="o1", symbol="HUNT", intent="open", requested_shares=10,
                               stop_price=D("90"), fill_session=world.days[FIRST], ref_price=D("100"), sector=None))
    assert led.state.epoch().committed_cash("momentum") == D("1000")
    with pytest.raises(LedgerError, match="committed"):
        led.append(ev.sleeve_funded(eid, t0, "momentum", D("-2500"), ref="sweep"))  # only $2,000 is uncommitted
    led.append(ev.sleeve_funded(eid, t0, "momentum", D("-2000"), ref="ok"))
    assert led.state.epoch().sleeves["momentum"].cash == D("1000")


def test_no_policy_means_fixed_sleeves_exactly_as_before(world):
    deps, led = play(world, sessions=30, capital=None)
    assert not decisions(led)
    assert [e.draft.payload["ref"] for e in led.store.read_all() if e.draft.kind is EventKind.SLEEVE_FUNDED] == ["d0-initial"] * 2


def test_previous_beneficiary_is_read_from_the_ledger(run):
    _, led = run
    events = led.store.read_all()
    assert previous_beneficiary(events, events[0].draft.epoch_id) in ("momentum", "contrarian")
    assert previous_beneficiary([], "x") is None


def test_evidence_matches_what_the_decision_recorded(run):
    deps, led = run
    events = led.store.read_all()
    first = decisions(led)[0]
    prefix = [e for e in events if e.seq < first.seq]
    st = LedgerState()
    for e in prefix:
        st = apply(st, e)
    built = build_evidence(P, prefix, st.epoch(), ["momentum", "contrarian"])
    assert {k: v.as_payload() for k, v in built.items()} == {k: dict(v) for k, v in first.draft.payload["evidence"].items()}
