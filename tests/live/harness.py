"""A synthetic 'vendor' and a temp-dir live system for the live-paper tests. Prices are NOT market data."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Mapping, Sequence

from tests.fixtures.competition_scenario import SPECS_COMP
from tests.fixtures.hunter_scenario import SEED, Seg, build_bars
from tests.fixtures.market import load_calendar
from the_reef.backtest import cache
from the_reef.live import epoch, market
from the_reef.live.config import EpochSpec, LivePaths
from the_reef.live.runner import RunReport, run
from the_reef.market.calendar import Session

D = Decimal
UTC = timezone.utc
CAL = load_calendar()
DAYS: list[date] = [d for d in (date.fromordinal(o) for o in range(CAL.first_day.toordinal(), CAL.last_day.toordinal() + 1)) if CAL.session(d)]
FLAT_EXTRA = tuple(f"ZF{c}" for c in "ABCDEFGHIJKLMNOPQRST")
SPECS = {k: v for k, v in SPECS_COMP.items() if k != "DEAL"}
UNIVERSE = tuple(sorted([*SPECS, *FLAT_EXTRA]))
FIRST_INDEX = 100  # sessions 0..99 are warmup; the epoch starts 2026-10-22
WARMUP = 60


def make_rows() -> dict[str, list[cache.RawRow]]:
    bars = []
    for sym, (start, _sector, vol, segs, skip) in SPECS.items():
        bars += build_bars(sym, start, segs, DAYS, SEED, vol, frozenset(skip))
    for i, sym in enumerate(FLAT_EXTRA):
        bars += build_bars(sym, 30.0 + i, [Seg(len(DAYS), 0.0, 0.005, 0.01)], DAYS, SEED, 400_000)
    bars += build_bars("SPY", 400.0, [Seg(len(DAYS), 0.0004, 0.004, 0.008)], DAYS, SEED, 50_000_000)
    out: dict[str, list[cache.RawRow]] = {}
    for b in bars:
        out.setdefault(b.symbol, []).append(cache.RawRow(b.day, b.open, b.high, b.low, b.close, b.close, b.volume, D("0"), D("0")))
    return out


ROWS = make_rows()


def session(day: date) -> Session:
    s = CAL.session(day)
    assert s is not None
    return s


def after_close(day: date, minutes: int = 45) -> datetime:
    return session(day).close + timedelta(minutes=minutes)


class Vendor:
    """What the data provider would return. ``edit`` lets a test damage, drop or restate rows."""

    name = "synthetic-vendor"

    def __init__(self) -> None:
        self.rows: dict[str, list[cache.RawRow]] = {k: list(v) for k, v in ROWS.items()}
        self.calls = 0
        self.fail = False

    def drop(self, symbol: str, day: date) -> None:
        self.rows[symbol] = [r for r in self.rows[symbol] if r.day != day]

    def replace(self, symbol: str, day: date, **fields) -> None:
        self.rows[symbol] = [cache.RawRow(**{**r.__dict__, **fields}) if r.day == day else r for r in self.rows[symbol]]

    def fetch(self, symbols: Sequence[str], start: date, end: date) -> Mapping[str, list[cache.RawRow]]:
        self.calls += 1
        if self.fail:
            raise ConnectionError("vendor unreachable")
        return {s: [r for r in self.rows.get(s, []) if start <= r.day < end] for s in symbols}


@dataclass
class Live:
    root: Path
    spec: EpochSpec
    paths: LivePaths
    vendor: Vendor = field(default_factory=Vendor)

    @staticmethod
    def create(tmp: Path, first_index: int = FIRST_INDEX) -> "Live":
        research = tmp / "research"
        for sym, rows in ROWS.items():
            cache.write(sym, rows, research)
        spec = EpochSpec.for_first_session(DAYS[first_index], universe=UNIVERSE, warmup_sessions=WARMUP)
        paths = LivePaths(tmp / "live", tmp / "checkpoints", tmp / "ui")
        market.seed(paths.market_dir, research, [*UNIVERSE, "SPY"], spec.first_session)
        return Live(tmp, spec, paths)

    def activate(self) -> dict:
        at = after_close(DAYS[DAYS.index(self.spec.first_session) - 1], 120)
        return epoch.activate(self.paths, self.spec, at, CAL)

    def run(self, now: datetime, *, fetch: bool = True, snapshot: bool = True) -> RunReport:
        return run(self.paths, self.spec, now, fetcher=self.vendor if fetch else None, calendar=CAL, write_snapshot=snapshot)

    def run_through(self, last: date) -> list[RunReport]:
        """One run per session day, each shortly after that day's close, as a scheduler would."""
        out = []
        i = DAYS.index(self.spec.first_session)
        while DAYS[i] <= last:
            out.append(self.run(after_close(DAYS[i])))
            i += 1
        return out

    def ledger(self):
        return epoch.open_ledger(self.paths, self.spec.epoch_id, writable=False)

    def kinds(self, kind: str) -> list:
        return [e for e in self.ledger().store.read_all() if e.draft.kind.value == kind]


def core(events) -> list[tuple]:
    """The ledger minus provenance records: what the sharks decided and what the books did."""
    return [(e.draft.kind.value, e.draft.event_id, e.draft.occurred_at.isoformat(), str(e.draft.payload)) for e in events
            if e.draft.kind.value != "ATTESTATION"]


def next_day(day: date) -> date:
    return DAYS[DAYS.index(day) + 1]


def prev_day(day: date) -> date:
    return DAYS[DAYS.index(day) - 1]
