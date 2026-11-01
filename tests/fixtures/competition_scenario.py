"""A deterministic, synthetic two-pod competition world (NOT market data).

Reuses the Hunter scenario's generator and symbols (HUNT breakout then gap-down, TRND slow trend then
break, DEAL pending cash acquisition, FLAT* noise) and adds three sold-off uptrends for Contrarian:

  DIPA  steady uptrend, sharp sell-off, then a rebound    -> Contrarian buys fear and is paid
  DIPB  steady uptrend, sharp sell-off that keeps falling -> Contrarian buys fear and is stopped out
  DIPC  a later, shallower sell-off and rebound

Same seeded generator as the Hunter fixtures: reruns are byte-identical.
"""
from __future__ import annotations

from decimal import Decimal

from tests.fixtures.hunter_scenario import EPOCH_ID, SPECS, START_INDEX, Seg, World, make_world
from the_reef.allocation.d0 import D0Config
from the_reef.engine.advance import EngineDeps, SleeveSpec
from the_reef.pods.registry import POD_REGISTRY, PodStatus
from the_reef.risk.limits import RiskLimits

D = Decimal
DIP_SPECS = {
    "DIPA": (60.0, "Consumer", 450_000, [
        Seg(66, 0.004, 0.004, 0.014), Seg(4, -0.03, 0.004, 0.02), Seg(14, 0.012, 0.004, 0.016), Seg(65, 0.0, 0.004, 0.012)], ()),
    "DIPB": (45.0, "Healthcare", 500_000, [
        Seg(70, 0.006, 0.004, 0.014), Seg(3, -0.03, 0.004, 0.02), Seg(30, -0.011, 0.004, 0.016), Seg(45, 0.0, 0.004, 0.012)], ()),
    "DIPC": (90.0, "Financials", 350_000, [
        Seg(97, 0.005, 0.004, 0.014), Seg(3, -0.03, 0.004, 0.02), Seg(12, 0.011, 0.004, 0.016), Seg(37, 0.0, 0.004, 0.012)], ()),
}
SPECS_COMP = {**{k: v for k, v in SPECS.items() if k not in ('BIGP', 'GAPR')}, **DIP_SPECS}
UNIVERSE = tuple(sorted(SPECS_COMP))
FIRST = START_INDEX
SESSIONS = 70  # sessions advanced in the demo
D0_MAX_NEW = 1  # Apex funds the single best idea per pod per session


def make_comp_world() -> World:
    return make_world(SPECS_COMP)


def make_comp_deps(world: World, limits: RiskLimits | None = None) -> EngineDeps:
    active = [p for p in POD_REGISTRY if p.status is PodStatus.ACTIVE]
    return EngineDeps(
        epoch_id=EPOCH_ID, calendar=world.calendar, instruments=world.master, actions=world.actions, bars=world.bars,
        limits=limits or RiskLimits(), d0=D0Config({p.pod_id: p.sleeve_weight for p in active}, max_new_per_session=D0_MAX_NEW),
        sleeves=[SleeveSpec(p.pod_id, p.make_strategy()) for p in active], universe=UNIVERSE,
    )
