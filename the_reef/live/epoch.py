"""Assembling a live-paper epoch: the same engine, strategies, limits and Apex policy as the fixture competition.

Nothing here tunes anything. ``build_deps`` takes the ACTIVE pods and their 30/30 sleeve weights from the registry
(the other 40% stays in Apex's central reserve), the default ``RiskLimits`` and the default C1 ``CapitalPolicy``.
The epoch's ``CHARTER`` attestation records all of it in the ledger when the epoch opens, and every run compares the
code it is running against that record: a changed strategy, limit or policy fails closed instead of silently changing
what the sharks do mid-epoch.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from the_reef.allocation.capital import CapitalPolicy
from the_reef.allocation.d0 import D0Config
from the_reef.backtest.history import CachedCalendar, HistoricalBarSource
from the_reef.backtest.universe import BENCHMARK
from the_reef.engine.advance import EngineDeps, SleeveSpec, bootstrap
from the_reef.execution.costs import ExecutionCosts
from the_reef.ledger import events as ev
from the_reef.ledger.events import canonical, digest
from the_reef.ledger.ledger import Ledger
from the_reef.live import market
from the_reef.live.config import EXECUTION_BASIS, PROVIDER, EpochSpec, LivePaths
from the_reef.live.store import CheckpointLog, FileEventStore, StoreCorrupt, verify_against
from the_reef.market.calendar import MarketCalendar, next_valid_open
from the_reef.market.instruments import StaticCorporateActions
from the_reef.pods.registry import POD_REGISTRY, PodStatus
from the_reef.risk.limits import RiskLimits

D0_MAX_NEW = 1  # Apex funds the single best idea per pod per session, as in the competition demonstration


class LiveError(RuntimeError):
    """A condition under which the live-paper system must stop and tell a human (the runner reports it as a SAFE_HOLD)."""


@dataclass
class Parts:
    deps: EngineDeps
    bars: HistoricalBarSource
    master: market.LiveInstrumentMaster
    calendar: MarketCalendar


def open_calendar() -> MarketCalendar:
    from the_reef.market.calendar import ExchangeCalendar  # noqa: PLC0415

    return CachedCalendar(ExchangeCalendar())  # type: ignore[return-value]


def build_deps(paths: LivePaths, spec: EpochSpec, now: datetime, calendar: MarketCalendar | None = None) -> Parts:
    cal = calendar or open_calendar()
    inner = HistoricalBarSource(cal, [*spec.universe, BENCHMARK], paths.market_dir)
    horizon = market.latest_finalized_session(cal, now)
    bars = market.VettedBars(inner, horizon.day if horizon else date.min)
    master = market.LiveInstrumentMaster(inner, cal, paths.market_dir)
    active = [p for p in POD_REGISTRY if p.status is PodStatus.ACTIVE]
    deps = EngineDeps(
        epoch_id=spec.epoch_id, calendar=cal, instruments=master, actions=StaticCorporateActions([]), bars=bars,  # type: ignore[arg-type]
        limits=RiskLimits(), d0=D0Config({p.pod_id: p.sleeve_weight for p in active}, max_new_per_session=D0_MAX_NEW),
        sleeves=[SleeveSpec(p.pod_id, p.make_strategy()) for p in active],  # type: ignore[misc]
        universe=spec.universe, initial_cash=spec.initial_cash, capital=CapitalPolicy(), costs=ExecutionCosts(),
    )
    return Parts(deps, inner, master, cal)


def _plain(x: Any) -> Any:
    if isinstance(x, Decimal):
        return format(x, "f")
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items()}
    return x


def charter(deps: EngineDeps, spec: EpochSpec) -> dict[str, Any]:
    """Everything the epoch's behaviour depends on, as plain data. Its digest pins the run."""
    return {
        "mode": "LIVE_DATA_PAPER", "paper_only": True, "execution_basis": EXECUTION_BASIS,
        "execution_note": "Fills are reconstructed after the close from the next session's daily open/high/low. They are not live intraday executions.",
        "first_session": spec.first_session.isoformat(), "initial_cash": format(spec.initial_cash, "f"),
        "data": {"provider": PROVIDER, "benchmark": BENCHMARK, "universe_size": len(deps.universe),
                 "universe_digest": digest(",".join(sorted(deps.universe))),
                 "finalize_delay_min": int(market.FINALIZE_DELAY.total_seconds() // 60), "min_coverage": format(market.MIN_COVERAGE, "f"),
                 "max_close_jump": format(market.MAX_CLOSE_JUMP, "f"), "halt_sessions": market.HALT_SESSIONS},
        "sleeves": {s.sleeve_id: f"{s.strategy.strategy_id}@{s.strategy.spec_hash}" for s in deps.sleeves},
        "sleeve_weights": {k: format(v, "f") for k, v in sorted(deps.d0.sleeve_weights.items())},
        "max_new_per_session": deps.d0.max_new_per_session,
        "limits": _plain(asdict(deps.limits)), "costs": _plain(asdict(deps.costs)),
        "capital_policy": deps.capital.describe() if deps.capital else None,
        "screen_untradable": deps.screen_untradable,
    }


def charter_hash(c: dict[str, Any]) -> str:
    return digest(canonical(c))


def open_checkpoints(paths: LivePaths, epoch_id: str) -> CheckpointLog:
    return CheckpointLog(paths.checkpoint_file(epoch_id))


def open_ledger(paths: LivePaths, epoch_id: str, *, writable: bool) -> Ledger:
    """Load the ledger, verifying the hash chain and every independently preserved checkpoint. Raises ``LiveError``."""
    cps = open_checkpoints(paths, epoch_id)
    try:
        store = FileEventStore(paths.ledger_file(epoch_id), writable=writable, checkpoints=cps if writable else None)
    except StoreCorrupt as exc:
        raise LiveError(f"ledger file is corrupt: {exc}") from exc
    problems = verify_against(store.read_all(), cps)
    if problems:
        raise LiveError("ledger does not match its preserved checkpoints: " + "; ".join(problems))
    try:
        ledger = Ledger(store, expected=cps.latest())
    except Exception as exc:  # noqa: BLE001 - chain break, truncation, invariant failure: all the same instruction to the human
        raise LiveError(f"ledger failed verification: {exc}") from exc
    if writable:
        store.sync_checkpoint()
    return ledger


def stored_charter(ledger: Ledger, epoch_id: str) -> dict[str, Any] | None:
    for e in ledger.store.read_all():
        if e.draft.kind is ev.EventKind.ATTESTATION and e.draft.payload.get("subtype") == "CHARTER":
            return ev.thaw(e.draft.payload)
    return None


def first_session_for(cal: MarketCalendar, activated_at: datetime) -> date:
    """The first session whose open is after ``activated_at``: decisions start there, never on a session already under way."""
    return next_valid_open(cal, activated_at).day


def activate(paths: LivePaths, spec: EpochSpec, activated_at: datetime, calendar: MarketCalendar | None = None) -> dict[str, Any]:
    """Open the epoch: EPOCH_OPENED, the 30/30 sleeves funded, and the CHARTER attestation. Writes no trade and no history.

    Refuses to run if the ledger already exists, if the first session is not strictly after ``activated_at``
    (that would be backfilling), or if any universe symbol lacks warmup history in the live cache.
    """
    from the_reef.live.store import WriterLock  # noqa: PLC0415

    cal = calendar or open_calendar()
    if first_session_for(cal, activated_at) > spec.first_session or cal.session(spec.first_session) is None:
        raise LiveError(f"{spec.first_session} is not a session after {activated_at.isoformat()}")
    if cal.session(spec.first_session).open <= activated_at:  # type: ignore[union-attr]
        raise LiveError("the first session has already opened; an epoch cannot start inside or after it")
    if paths.ledger_file(spec.epoch_id).exists() and paths.ledger_file(spec.epoch_id).stat().st_size:
        raise LiveError(f"epoch {spec.epoch_id} already has a ledger; refusing to touch it")
    parts = build_deps(paths, spec, activated_at, cal)
    short = warmup_shortfalls(parts.bars, spec)
    if short:
        raise LiveError("not enough warmup history: " + ", ".join(f"{s} ({n})" for s, n in sorted(short.items())[:8]))
    with WriterLock(paths.lock_file(spec.epoch_id)):
        ledger = open_ledger(paths, spec.epoch_id, writable=True)
        bootstrap(ledger, parts.deps, activated_at)
        c = charter(parts.deps, spec)
        ledger.append(ev.attestation(spec.epoch_id, activated_at, subtype="CHARTER", key="charter",
                                     detail={"charter": c, "charter_hash": charter_hash(c), "activated_at": activated_at.isoformat()}))
        store = ledger.store
        store.sync_checkpoint()  # type: ignore[attr-defined]
    return c


def warmup_shortfalls(bars: HistoricalBarSource, spec: EpochSpec) -> dict[str, int]:
    """Symbols with fewer than ``spec.warmup_sessions`` bars before the first session (the benchmark included)."""
    out = {}
    for s in [*spec.universe, BENCHMARK]:
        n = sum(1 for d in bars.days(s) if d < spec.first_session)
        if n < spec.warmup_sessions:
            out[s] = n
    return out


def check_charter(ledger: Ledger, parts: Parts, spec: EpochSpec) -> None:
    stored = stored_charter(ledger, spec.epoch_id)
    if stored is None:
        raise LiveError("the ledger has no CHARTER attestation; this is not an activated live-paper epoch")
    now_c = charter(parts.deps, spec)
    if charter_hash(now_c) != stored["charter_hash"]:
        diff = sorted(k for k in now_c if now_c[k] != stored["charter"].get(k))
        raise LiveError("the code now differs from the epoch's CHARTER (" + ", ".join(diff) + "); strategies, limits and policy may not change mid-epoch")

