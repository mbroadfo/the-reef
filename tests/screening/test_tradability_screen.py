"""Eligibility before ranking: an untradable name must not take a candidate or allocator slot from a tradable one."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tests.fixtures.competition_scenario import FIRST, SESSIONS, make_comp_deps, make_comp_world
from tests.hunter.test_engine_safety import Crash, CrashingStore
from the_reef.allocation.capital import CapitalPolicy, build_evidence
from the_reef.allocation.d0 import D0Config
from the_reef.engine.advance import DECISION_DELAY, NoteKind, SleeveSpec, advance, bootstrap, next_session_to_advance
from the_reef.execution.gate import screen_candidate
from the_reef.ledger.events import EventKind
from the_reef.ledger.ledger import InMemoryEventStore, Ledger
from the_reef.market.instruments import CorporateAction, CorporateActionKind, Intent, StaticCorporateActions, TradabilityCode
from the_reef.strategy.base import Proposal, Review, StrategyContext

D = Decimal


# --- a strategy whose ranking we control; it applies its own candidate cap exactly as Hunter and Contrarian do ----------

@dataclass
class Ranked:
    scores: dict[str, int]
    cap: int = 2
    strategy_id: str = "ranked-stub"
    spec_hash: str = "0" * 16

    def propose(self, ctx: StrategyContext) -> list[Proposal]:
        names = [s for s in self.scores if s in ctx.bars and s not in ctx.holdings and s not in ctx.blocked]
        names.sort(key=lambda s: (-self.scores[s], s))
        out = []
        for s in names[: self.cap]:
            close = ctx.bars[s][-1].close
            out.append(Proposal(s, Intent.OPEN, D(self.scores[s]), close, (close * D("0.95")).quantize(D("0.01")), f"stub score {self.scores[s]}"))
        return out

    def review(self, ctx: StrategyContext) -> Review:
        return Review()


@pytest.fixture(scope="module")
def world():
    return make_comp_world()


def stub_deps(world, scores=None, *, screen=True, actions=None, cap=2):
    base = make_comp_deps(world, capital=None)
    return replace(base, sleeves=[SleeveSpec("momentum", Ranked(scores or {"DEAL": 9, "DIPA": 5, "DIPB": 4}, cap=cap))],
                   d0=D0Config({"momentum": D("0.30")}, max_new_per_session=1), screen_untradable=screen,
                   actions=actions or base.actions)


def play(world, deps, sessions):
    led = Ledger()
    bootstrap(led, deps, world.calendar.session(world.days[FIRST]).open - timedelta(hours=1))
    reports = [advance(led, deps, world.days[i]) for i in range(FIRST, FIRST + sessions)]
    return led, reports


def of_kind(led, kind):
    return [e for e in led.store.read_all() if e.draft.kind is kind]


def symbols(led, kind):
    return [e.draft.payload["symbol"] for e in of_kind(led, kind)]


def deal_known_at(world, when: datetime):
    return StaticCorporateActions([CorporateAction("DEAL", CorporateActionKind.CASH_ACQUISITION, announced=world.days[10],
                                                   effective=world.days[140], known_at=when, cash_per_share=D("95.00"),
                                                   evidence=("synthetic-deal",))])


def decide_at(world, index=FIRST):
    return world.calendar.session(world.days[index]).close + DECISION_DELAY


# --- the core defect and its correction ----------------------------------------------------------------------------

def test_a_high_ranked_untradable_name_no_longer_displaces_two_tradable_alternatives(world):
    # Before: the cap of 2 keeps DEAL and DIPA, D0's one slot goes to DEAL, the gate refuses it, DIPA is rank-capped and
    # DIPB is never seen: nothing is bought although two tradable names signalled.
    led, _ = play(world, stub_deps(world, screen=False), 1)
    assert symbols(led, EventKind.PROPOSAL_SUBMITTED) == ["DEAL", "DIPA"]
    assert of_kind(led, EventKind.ORDER_QUEUED) == []
    assert not of_kind(led, EventKind.OPPORTUNITY_SUPPRESSED)

    # After: DEAL is withheld before the cap, so DIPA and DIPB are proposed and D0's slot funds DIPA.
    led, reports = play(world, stub_deps(world), 1)
    assert symbols(led, EventKind.PROPOSAL_SUBMITTED) == ["DIPA", "DIPB"]
    decisions = {e.draft.payload["proposal_id"].split(":")[-1]: e.draft.payload for e in of_kind(led, EventKind.APEX_DECISION)}
    assert decisions["DIPA"]["outcome"] == "FUNDED" and list(decisions["DIPB"]["reasons"]) == ["D0_RANK_CAP"]
    assert symbols(led, EventKind.ORDER_QUEUED) == ["DIPA"]
    assert [n.symbol for n in reports[0].notes if n.kind is NoteKind.SUPPRESSED] == ["DEAL"]


def test_with_nothing_untradable_the_screen_changes_nothing(world):
    names = {"DIPA": 5, "DIPB": 4, "DIPC": 3}
    on, _ = play(world, stub_deps(world, names), 5)
    off, _ = play(world, stub_deps(world, names, screen=False), 5)
    assert on.state.head_hash == off.state.head_hash
    assert not of_kind(on, EventKind.OPPORTUNITY_SUPPRESSED)


def test_defaults_and_boundaries_are_unchanged(world):
    deps = make_comp_deps(world)
    assert deps.screen_untradable is True
    assert deps.d0.max_new_per_session == 1
    assert all(getattr(s.strategy, "base", s.strategy).params.max_candidates == 2 for s in deps.sleeves)
    assert all(s.strategy.request_fraction == D("0.5") for s in deps.sleeves)
    assert CapitalPolicy().describe() == {
        "version": "C1", "review_every": "10", "min_history": "15", "lookback": "20", "drawdown_weight": "0.5", "margin": "0.02",
        "flip_margin": "0.04", "step_pct": "0.05", "round_to": "10", "min_transfer": "100", "floor_pct": "0.5", "cap_pct": "0.5",
        "reserve_floor_pct": "0.1", "min_proposals": "3"}


# --- the audit trail -----------------------------------------------------------------------------------------------

def test_every_withheld_signal_is_recorded_with_instrument_signal_reason_and_decision_time(world):
    led, _ = play(world, stub_deps(world), 3)
    sup = of_kind(led, EventKind.OPPORTUNITY_SUPPRESSED)
    assert len(sup) == 3
    first = sup[0]
    p = first.draft.payload
    assert (p["sleeve_id"], p["symbol"], p["session_day"], p["rule"], p["reason"]) == (
        "momentum", "DEAL", world.days[FIRST].isoformat(), "TRADABILITY_SCREEN", "PENDING_CASH_DEAL")
    assert p["signal"]["score"] == "9" and p["signal"]["strategy"] == "ranked-stub@" + "0" * 16 and p["intent"] == "open"
    assert "pending cash acquisition" in p["detail"] and p["counted_as_proposal"] is False
    assert p["decided_at"] == first.draft.occurred_at.isoformat() == decide_at(world).isoformat()
    # withheld means withheld: not a proposal, a decision, a rejection, an order or a fill
    for kind in (EventKind.PROPOSAL_SUBMITTED, EventKind.ORDER_REJECTED, EventKind.ORDER_QUEUED, EventKind.FILL):
        assert "DEAL" not in symbols(led, kind)


def test_every_signal_is_audited_even_when_it_would_have_been_cut_by_the_candidate_cap(world):
    deps = stub_deps(world, {"DEAL": 9, "DIPA": 5, "DIPB": 4}, cap=1)
    led, _ = play(world, deps, 1)
    assert symbols(led, EventKind.OPPORTUNITY_SUPPRESSED) == ["DEAL"]
    assert symbols(led, EventKind.PROPOSAL_SUBMITTED) == ["DIPA"]


# --- point in time ---------------------------------------------------------------------------------------------------

def test_a_corporate_action_not_yet_public_cannot_suppress_anything(world):
    at = decide_at(world)
    led, _ = play(world, stub_deps(world, actions=deal_known_at(world, at + timedelta(seconds=1))), 1)
    assert not of_kind(led, EventKind.OPPORTUNITY_SUPPRESSED)
    assert "DEAL" in symbols(led, EventKind.PROPOSAL_SUBMITTED)
    led, _ = play(world, stub_deps(world, actions=deal_known_at(world, at)), 1)
    assert symbols(led, EventKind.OPPORTUNITY_SUPPRESSED) == ["DEAL"]


def test_the_screen_answers_exactly_as_the_gate_does_at_the_knowledge_time(world):
    at = decide_at(world)
    for known, expect_ok in ((at + timedelta(microseconds=1), True), (at, False)):
        deps = stub_deps(world, actions=deal_known_at(world, known))
        res = screen_candidate(deps.ports, "DEAL", Intent.OPEN, at)
        assert res is not None and res.ok is expect_ok
        if not expect_ok:
            assert res.code is TradabilityCode.PENDING_CASH_DEAL
    assert screen_candidate(deps.ports, "DIPA", Intent.OPEN, at).ok
    assert screen_candidate(deps.ports, "NOPE", Intent.OPEN, at).code is TradabilityCode.UNKNOWN_SYMBOL


def test_tradability_that_changes_before_the_fill_is_still_refused_at_the_open(world):
    # Eligible at the close (the deal is not public yet); public before the next open: the fill gate must still refuse it.
    deps = stub_deps(world, {"DEAL": 9}, actions=deal_known_at(world, decide_at(world) + timedelta(hours=1)))
    led, _ = play(world, deps, 2)
    assert not any(e.draft.payload["session_day"] == world.days[FIRST].isoformat() for e in of_kind(led, EventKind.OPPORTUNITY_SUPPRESSED))
    assert symbols(led, EventKind.ORDER_QUEUED)[0] == "DEAL"
    [rej] = [e for e in of_kind(led, EventKind.ORDER_REJECTED) if e.draft.payload["stage"] == "FILL"]
    assert rej.draft.payload["code"].startswith("INSTRUMENT_NOT_TRADABLE") and "PENDING_CASH_DEAL" in rej.draft.payload["code"]
    assert of_kind(led, EventKind.FILL) == []


def test_a_name_already_held_is_not_a_suppression(world):
    # Bought while still tradable; the deal then becomes public. The holding is not re-screened and nothing is "suppressed".
    deps = stub_deps(world, {"DEAL": 9}, actions=deal_known_at(world, decide_at(world) + timedelta(days=1)))
    led, _ = play(world, deps, 4)
    assert of_kind(led, EventKind.FILL) and "DEAL" in led.state.epoch().sleeves["momentum"].positions
    assert not any(e.draft.payload["session_day"] > world.days[FIRST + 1].isoformat() for e in of_kind(led, EventKind.OPPORTUNITY_SUPPRESSED))


# --- the demonstration run -----------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def demo(world):
    deps = make_comp_deps(world)
    led, _ = play(world, deps, SESSIONS)
    return deps, led


def test_the_demo_withholds_deal_and_only_deal_and_never_buys_it(demo):
    _, led = demo
    sup = of_kind(led, EventKind.OPPORTUNITY_SUPPRESSED)
    assert sup and {e.draft.payload["symbol"] for e in sup} == {"DEAL"}
    assert {e.draft.payload["reason"] for e in sup} == {"PENDING_CASH_DEAL"}
    assert "DEAL" not in symbols(led, EventKind.PROPOSAL_SUBMITTED) + symbols(led, EventKind.FILL)
    keys = [(e.draft.payload["sleeve_id"], e.draft.payload["session_day"], e.draft.payload["symbol"]) for e in sup]
    assert len(keys) == len(set(keys)), "one record per pod, day and instrument"
    assert not [e for e in of_kind(led, EventKind.ORDER_REJECTED) if "PENDING_CASH_DEAL" in e.draft.payload["code"]], "the gate is now a backstop"


def test_untradable_signals_do_not_count_toward_c1_proposal_evidence(demo):
    deps, led = demo
    ep = led.state.epoch()
    ev = build_evidence(deps.capital, led.store.read_all(), ep, ["momentum", "contrarian"])
    first_window_day = sorted(ep.marks)[-deps.capital.lookback]
    for pid, e in ev.items():
        submitted = [x for x in of_kind(led, EventKind.PROPOSAL_SUBMITTED)
                     if x.draft.payload["pod_id"] == pid and x.draft.payload["as_of_session"] >= first_window_day]
        assert e.proposals == len(submitted), "C1 counts the proposals Apex was shown, and only those"
    reviews = {e.draft.payload["review_id"]: e.draft.payload for e in of_kind(led, EventKind.APEX_CAPITAL_DECISION)}
    r35 = reviews["review-035"]
    assert r35["evidence"]["momentum"]["proposals"] < deps.capital.min_proposals
    # Documented consequence on this fixture: the threshold is unchanged; the withheld DEAL signals no longer pad the count.
    assert list(r35["reasons"]) == ["LEADER_CANNOT_DEPLOY"]


# --- recovery, idempotency, look-ahead ---------------------------------------------------------------------------

def test_replaying_a_finished_run_appends_nothing_and_rebuilds_the_same_state(demo, world):
    deps, led = demo
    head = led.state.head_hash
    assert advance(led, deps, world.days[FIRST + SESSIONS - 1]).appended == 0
    assert led.state.head_hash == head
    assert Ledger(InMemoryEventStore(led.store.read_all())).state.digest() == led.state.digest()


def test_a_crash_around_every_suppression_and_across_the_run_resumes_to_the_identical_ledger(demo, world):
    _, expected = demo
    sup = [e.seq for e in of_kind(expected, EventKind.OPPORTUNITY_SUPPRESSED)]
    total = len(expected.store.read_all())
    targets = sorted({t for s in sup[:3] for t in range(s - 2, s + 3)} | set(range(7, total, 67)))
    for crash_at in targets:
        deps = make_comp_deps(world)
        store = CrashingStore(crash_at)
        led = Ledger(store)
        with pytest.raises(Crash):
            bootstrap(led, deps, world.calendar.session(world.days[FIRST]).open - timedelta(hours=1))
            for i in range(FIRST, FIRST + SESSIONS):
                advance(led, deps, world.days[i])
        revived = Ledger(InMemoryEventStore(store.read_all()))
        bootstrap(revived, deps, world.calendar.session(world.days[FIRST]).open - timedelta(hours=1))
        for i in range(world.days.index(next_session_to_advance(revived, deps, world.days[FIRST])), FIRST + SESSIONS):
            advance(revived, deps, world.days[i])
        assert revived.state.head_hash == expected.state.head_hash, f"diverged after a crash at append {crash_at}"


def test_nothing_after_a_session_changes_what_was_decided_in_it(demo, world):
    _, full = demo
    short, _ = play(world, make_comp_deps(world), 40)
    a, b = short.store.read_all(), full.store.read_all()
    assert [e.hash for e in a] == [e.hash for e in b[: len(a)]]
    assert any(e.draft.kind is EventKind.OPPORTUNITY_SUPPRESSED for e in a)
