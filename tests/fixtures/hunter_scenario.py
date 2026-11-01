"""A synthetic, fully deterministic market for the Hunter vertical slice.

NOT real market data. Prices are generated from fixed segments plus seeded noise so that each
behaviour of the engine is exercised on a known day:

  HUNT  flat, then a strong rally, then a large opening gap DOWN through its trailing stop
  TRND  slow low-volatility uptrend with wide intraday ranges, then a decline: the trend-break exit
  BIGP  breaks out but costs $1,500 a share, more than the 10% position cap on a $10,000 fund
  DEAL  breaks out while a definitive cash acquisition is pending (the SEM lesson, E-9)
  GAPR  breaks out but its next session has no official open print (missing data at the fill)
  FLATA..3  range-bound noise that never triggers

Sessions come from the cached NYSE calendar fixture (2026-06-01 .. 2026-12-31).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Sequence

from tests.fixtures.market import load_calendar
from the_reef.allocation.d0 import D0Config
from the_reef.engine.advance import EngineDeps, SleeveSpec
from the_reef.market.bars import DailyBar, StaticBarSource
from the_reef.market.instruments import (
    CorporateAction,
    CorporateActionKind,
    InstrumentRecord,
    InstrumentStatus,
    StaticCorporateActions,
    StaticInstrumentMaster,
)
from the_reef.risk.limits import RiskLimits
from the_reef.strategy.hunter import Hunter

D = Decimal
UTC = timezone.utc
CENT = D("0.01")
EPOCH_ID = "epoch-1"
SLEEVE = "hunter"
START_INDEX = 55  # first session advanced: 56 bars exist, enough for the 50-day trend filter


def q(x: float | Decimal) -> Decimal:
    return D(str(x)).quantize(CENT, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class Seg:
    n: int
    drift: float = 0.0  # mean close-to-close return per session
    noise: float = 0.004  # close noise (uniform +-)
    rng: float = 0.012  # intraday high-low range as a fraction of price
    gap: float = 0.0  # opening gap vs previous close (applied to the first session of the segment)


def build_bars(symbol: str, start: float, segs: Sequence[Seg], days: Sequence[date], seed: int, volume: int,
               skip: frozenset[int] = frozenset()) -> list[DailyBar]:
    rnd = random.Random(f"{seed}-{symbol}")
    out: list[DailyBar] = []
    prev = D(str(start))
    i = 0
    for seg in segs:
        for k in range(seg.n):
            if i >= len(days):
                break
            gap = seg.gap if k == 0 else 0.0
            move = rnd.uniform(-seg.noise, seg.noise)
            o = q(prev * D(str(1 + gap))) if gap else q(prev * D(str(1 + rnd.uniform(-seg.noise, seg.noise) * 0.3)))
            c = q(o * D(str(1 + seg.drift + move)))
            hi = q(max(o, c) * D(str(1 + seg.rng * rnd.uniform(0.3, 0.5))))
            lo = q(min(o, c) * D(str(1 - seg.rng * rnd.uniform(0.3, 0.5))))
            vol = int(volume * rnd.uniform(0.8, 1.2))
            if i not in skip:
                out.append(DailyBar(symbol, days[i], o, hi, lo, c, vol, "synthetic"))
            prev = c
            i += 1
    return out


# (symbol, start price, sector, volume, segments, indexes of sessions with no bar)
SPECS = {
    "HUNT": (100.0, "Technology", 200_000, [
        Seg(65, 0.0, 0.008, 0.014), Seg(14, 0.016, 0.004, 0.016), Seg(17, 0.004, 0.004, 0.014),
        Seg(1, -0.003, 0.002, 0.02, gap=-0.12), Seg(60, 0.0, 0.006, 0.014)], ()),
    "TRND": (50.0, "Industrials", 400_000, [
        Seg(70, 0.0, 0.001, 0.02), Seg(26, 0.0035, 0.0008, 0.03), Seg(15, -0.011, 0.0008, 0.03), Seg(40, 0.0, 0.002, 0.02)], ()),
    "BIGP": (1500.0, "Healthcare", 6_000, [
        Seg(75, 0.0, 0.006, 0.012), Seg(11, 0.015, 0.003, 0.014), Seg(63, 0.0, 0.006, 0.012)], ()),
    "DEAL": (80.0, "Financials", 150_000, [
        Seg(80, 0.0, 0.006, 0.012), Seg(11, 0.015, 0.003, 0.014), Seg(58, 0.0, 0.004, 0.01)], ()),
    "GAPR": (60.0, "Utilities", 300_000, [
        Seg(85, 0.0, 0.006, 0.012), Seg(8, 0.015, 0.003, 0.014), Seg(56, 0.0, 0.004, 0.01)], (57,)),
    "FLATA": (40.0, "Consumer", 500_000, [Seg(149, 0.0, 0.006, 0.012)], ()),
    "FLATB": (25.0, "Energy", 700_000, [Seg(149, 0.0, 0.005, 0.01)], ()),
    "FLATC": (70.0, "Materials", 300_000, [Seg(149, 0.0, 0.007, 0.012)], ()),
}
UNIVERSE = tuple(sorted(SPECS))
SEED = 20261031


@dataclass(frozen=True)
class World:
    calendar: object
    bars: StaticBarSource
    master: StaticInstrumentMaster
    actions: StaticCorporateActions
    days: list[date]


def make_world() -> World:
    cal = load_calendar()
    days: list[date] = []
    d = cal.first_day
    while d <= cal.last_day:
        if cal.session(d) is not None:
            days.append(d)
        d = date.fromordinal(d.toordinal() + 1)
    bars: list[DailyBar] = []
    records: list[InstrumentRecord] = []
    for sym, (start, sector, vol, segs, skip) in SPECS.items():
        bars.extend(build_bars(sym, start, segs, days, SEED, vol, frozenset(skip)))
        records.append(InstrumentRecord(sym, "NYSE", InstrumentStatus.ACTIVE, date(2010, 1, 4), None, sector,
                                        "synthetic", datetime(2020, 1, 1, tzinfo=UTC)))
    deal = CorporateAction("DEAL", CorporateActionKind.CASH_ACQUISITION, announced=days[10], effective=days[140],
                           known_at=datetime(2026, 6, 15, tzinfo=UTC), cash_per_share=D("95.00"),
                           evidence=("synthetic-deal",))
    return World(cal, StaticBarSource(bars, cal), StaticInstrumentMaster(records), StaticCorporateActions([deal]), days)


def make_deps(world: World, weight: Decimal = D("0.40"), limits: RiskLimits | None = None) -> EngineDeps:
    return EngineDeps(
        epoch_id=EPOCH_ID, calendar=world.calendar, instruments=world.master, actions=world.actions, bars=world.bars,
        limits=limits or RiskLimits(), d0=D0Config({SLEEVE: weight}, max_new_per_session=2),
        sleeves=[SleeveSpec(SLEEVE, Hunter())], universe=UNIVERSE,
    )
