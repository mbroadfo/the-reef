"""Instrument identity, tradability and corporate-action validation (requirements I-1, I-2, I-3, I-5).

Interfaces plus pure checks. Where the data comes from (yfinance, SEC EDGAR, a database) is
decided later behind ``InstrumentMaster`` and ``CorporateActionSource``; this module never
fetches anything.

Why it exists: Reef 1.0 recorded a purchase of SEM on 2026-07-02, the day after the company's
cash acquisition closed and its stock stopped trading (defect E-9).
"""
from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Collection, Protocol, Sequence, runtime_checkable

from the_reef.market.calendar import MarketCalendar, session_age_days

_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}([.-][A-Z])?$")


class InvalidSymbol(ValueError):
    pass


def _require_aware(ts: datetime, what: str) -> None:
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError(f"{what} must be timezone-aware")


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def normalize_symbol(raw: str) -> str:
    """Upper-case, trimmed exchange symbol; raises ``InvalidSymbol`` for anything else.

    Deliberately strict: no spaces, digits, punctuation other than one class suffix
    ("BRK.B" or "BRK-B"), no empty strings, no leading ``$``.
    """
    if not isinstance(raw, str):
        raise InvalidSymbol(f"symbol must be a string, got {type(raw).__name__}")
    cleaned = raw.strip().upper()
    if not _SYMBOL_RE.match(cleaned):
        raise InvalidSymbol(f"not a valid exchange symbol: {raw!r}")
    return cleaned


class InstrumentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    HALTED = "HALTED"
    DELISTED = "DELISTED"
    ACQUIRED = "ACQUIRED"


@dataclass(frozen=True)
class InstrumentRecord:
    symbol: str
    exchange: str
    status: InstrumentStatus
    first_trade_date: date
    last_trade_date: date | None  # last session the instrument traded, when known
    sector: str | None
    source: str
    as_of: datetime  # vintage: when this was known; explicit so history cannot leak forward

    def __post_init__(self) -> None:
        _require_aware(self.as_of, "InstrumentRecord.as_of")


class CorporateActionKind(str, Enum):
    CASH_ACQUISITION = "CASH_ACQUISITION"
    DELISTING = "DELISTING"


@dataclass(frozen=True)
class CorporateAction:
    symbol: str
    kind: CorporateActionKind
    announced: date
    effective: date  # first day the shares no longer exist / trade
    known_at: datetime  # when the action became public
    cash_per_share: Decimal | None = None
    evidence: tuple[str, ...] = field(default_factory=tuple)  # filing ids / URLs

    def __post_init__(self) -> None:
        _require_aware(self.known_at, "CorporateAction.known_at")

    @property
    def action_id(self) -> str:
        """Stable identity: one real-world action keeps one id across restatements, re-fetches
        and evidence updates. Cash terms and evidence are deliberately excluded."""
        return _digest("corporate_action", self.symbol, self.kind.value, self.effective.isoformat())


@runtime_checkable
class InstrumentMaster(Protocol):
    def get(self, symbol: str, as_of: datetime) -> InstrumentRecord | None:
        """The newest record for ``symbol`` whose vintage is at or before ``as_of``.

        Point in time: never return knowledge dated after ``as_of`` (a later delisting, status or
        last-trade date). An adapter over live data that cannot answer point-in-time must refuse
        the query rather than return today's record.
        """
        ...


@runtime_checkable
class CorporateActionSource(Protocol):
    def actions_for(self, symbol: str, as_of: datetime) -> Sequence[CorporateAction]:
        """Actions for ``symbol`` publicly known at ``as_of`` (``known_at <= as_of``), one entry
        per ``action_id`` (the latest version known at ``as_of``)."""
        ...


class Intent(str, Enum):
    OPEN = "open"
    ADD = "add"
    REDUCE = "reduce"
    CLOSE = "close"

    @property
    def adds_exposure(self) -> bool:
        return self in (Intent.OPEN, Intent.ADD)


class TradabilityCode(str, Enum):
    OK = "OK"
    INVALID_SYMBOL = "INVALID_SYMBOL"
    UNKNOWN_SYMBOL = "UNKNOWN_SYMBOL"
    HALTED = "HALTED"
    DELISTED = "DELISTED"
    ACQUIRED = "ACQUIRED"
    NOT_YET_LISTED = "NOT_YET_LISTED"
    PENDING_CASH_DEAL = "PENDING_CASH_DEAL"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


@dataclass(frozen=True)
class TradabilityResult:
    ok: bool
    code: TradabilityCode
    detail: str = ""
    evidence: tuple[str, ...] = ()


def _blocked(code: TradabilityCode, detail: str, evidence: tuple[str, ...] = ()) -> TradabilityResult:
    return TradabilityResult(False, code, detail, evidence)


def check_tradable(
    symbol: str,
    session_day: date,
    master: InstrumentMaster,
    actions: CorporateActionSource,
    calendar: MarketCalendar,
    *,
    intent: Intent,
    as_of: datetime,
    min_history_sessions: int = 60,
) -> TradabilityResult:
    """May ``intent`` be executed in ``symbol`` on the session ``session_day``?

    ``as_of`` is the knowledge time (decision or fill time). Instrument facts and corporate
    actions are read as they were known then, so a backtest cannot see a later delisting.

    Rules, in order:
      1. The symbol must be well formed and known (no guessing from a stale quote).
      2. Not yet listed, delisted, acquired or halted on that session blocks every intent,
         including selling. A held name that disappears must be settled by a corporate-action
         cash-out (``settlements_due``), never by a simulated sale.
      3. A known cash acquisition already effective blocks every intent, whatever the master says.
      4. Opening or adding is also blocked while a definitive cash deal is pending (price pinned,
         no upside) and while the listing is younger than ``min_history_sessions``.
    """
    try:
        sym = normalize_symbol(symbol)
    except InvalidSymbol as exc:
        return _blocked(TradabilityCode.INVALID_SYMBOL, str(exc))

    _require_aware(as_of, "as_of")
    record = master.get(sym, as_of)
    if record is None:
        return _blocked(TradabilityCode.UNKNOWN_SYMBOL, f"{sym} is not in the instrument master")

    if session_day < record.first_trade_date:
        return _blocked(TradabilityCode.NOT_YET_LISTED, f"{sym} first traded {record.first_trade_date}")

    gone = record.last_trade_date is not None and session_day > record.last_trade_date
    if record.status in (InstrumentStatus.DELISTED, InstrumentStatus.ACQUIRED) and (
        gone or record.last_trade_date is None
    ):
        code = TradabilityCode.ACQUIRED if record.status is InstrumentStatus.ACQUIRED else TradabilityCode.DELISTED
        last = record.last_trade_date.isoformat() if record.last_trade_date else "unknown"
        evidence = tuple(a for act in actions.actions_for(sym, as_of) for a in act.evidence)
        return _blocked(code, f"{sym} not tradable on {session_day}; last traded {last}", evidence)

    # A cash deal known at ``as_of`` that is already effective ends trading even if the master
    # has not caught up; settle via ``settlements_due``, never by trading.
    for act in actions.actions_for(sym, as_of):
        if act.kind is CorporateActionKind.CASH_ACQUISITION and act.effective <= session_day:
            return _blocked(
                TradabilityCode.ACQUIRED,
                f"{sym} cash acquisition effective {act.effective}; shares no longer trade",
                act.evidence,
            )

    if record.status is InstrumentStatus.HALTED:
        return _blocked(TradabilityCode.HALTED, f"{sym} is halted")

    if intent.adds_exposure:
        for act in actions.actions_for(sym, as_of):
            if act.kind is CorporateActionKind.CASH_ACQUISITION and act.announced <= session_day <= act.effective:
                return _blocked(
                    TradabilityCode.PENDING_CASH_DEAL,
                    f"{sym} has a pending cash acquisition effective {act.effective}",
                    act.evidence,
                )
        history = session_age_days(calendar, record.first_trade_date, session_day)
        if history < min_history_sessions:
            return _blocked(
                TradabilityCode.INSUFFICIENT_HISTORY,
                f"{sym} has {history} sessions of history; {min_history_sessions} required",
            )

    return TradabilityResult(True, TradabilityCode.OK)


@dataclass(frozen=True)
class CashOut:
    """A cash-out of one holder's shares. ``event_id`` is the ledger idempotency key."""

    symbol: str
    shares: int
    cash: Decimal
    effective: date
    evidence: tuple[str, ...]
    action_id: str
    holder: str
    event_id: str

    @property
    def fingerprint(self) -> str:
        """Content hash. A ledger that sees a known ``event_id`` with a different fingerprint
        must raise, not silently skip or overwrite."""
        return _digest(self.event_id, str(self.shares), str(self.cash))


def settlements_due(
    holdings: dict[str, int],
    actions: CorporateActionSource,
    session_day: date,
    *,
    holder: str,
    as_of: datetime,
    already_settled: Collection[str] = (),
) -> list[CashOut]:
    """Cash-out events for ``holder``'s names whose acquisition took effect on or before ``session_day``.

    The caller records them as ledger ``corporate_action`` events. Whole shares times the filed
    per-share price; nothing is estimated from a quote.

    Identity: ``event_id`` = digest(action_id, holder), stable across re-runs, restated source
    records and duplicate source rows. ``already_settled`` holds the event ids the ledger has
    recorded; those are skipped, so calling this every session is idempotent. Ids are scoped
    per holder (sleeve): two sleeves holding the same name settle independently.
    """
    _require_aware(as_of, "as_of")
    out: dict[str, CashOut] = {}
    for sym, shares in sorted(holdings.items()):
        if shares <= 0:
            continue
        for act in actions.actions_for(sym, as_of):
            if not (
                act.kind is CorporateActionKind.CASH_ACQUISITION
                and act.cash_per_share is not None
                and act.effective <= session_day
            ):
                continue
            event_id = _digest("cash_out", act.action_id, holder)
            if event_id in already_settled or event_id in out:
                continue
            out[event_id] = CashOut(
                sym, shares, act.cash_per_share * shares, act.effective, act.evidence, act.action_id, holder, event_id
            )
    return list(out.values())


class StaticInstrumentMaster:
    """In-memory master for tests and cached data; keeps every vintage of a symbol."""

    def __init__(self, records: Sequence[InstrumentRecord]) -> None:
        self._by_symbol: dict[str, list[InstrumentRecord]] = {}
        for r in records:
            self._by_symbol.setdefault(r.symbol, []).append(r)
        for versions in self._by_symbol.values():
            versions.sort(key=lambda r: r.as_of)

    def get(self, symbol: str, as_of: datetime) -> InstrumentRecord | None:
        known = [r for r in self._by_symbol.get(symbol, ()) if r.as_of <= as_of]
        return known[-1] if known else None


class StaticCorporateActions:
    def __init__(self, actions: Sequence[CorporateAction]) -> None:
        self._by_symbol: dict[str, list[CorporateAction]] = {}
        for a in actions:
            self._by_symbol.setdefault(a.symbol, []).append(a)

    def actions_for(self, symbol: str, as_of: datetime) -> Sequence[CorporateAction]:
        latest: dict[str, CorporateAction] = {}
        for a in sorted(self._by_symbol.get(symbol, ()), key=lambda a: a.known_at):
            if a.known_at <= as_of:
                latest[a.action_id] = a
        return tuple(latest.values())
