"""Instrument identity, tradability and corporate-action validation (requirements I-1, I-2, I-3, I-5).

Interfaces plus pure checks. Where the data comes from (yfinance, SEC EDGAR, a database) is
decided later behind ``InstrumentMaster`` and ``CorporateActionSource``; this module never
fetches anything.

Why it exists: Reef 1.0 recorded a purchase of SEM on 2026-07-02, the day after the company's
cash acquisition closed and its stock stopped trading (defect E-9).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol, Sequence, runtime_checkable

from the_reef.market.calendar import MarketCalendar, session_age_days

_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}([.-][A-Z])?$")


class InvalidSymbol(ValueError):
    pass


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
    last_trade_date: date | None = None  # last session the instrument traded, when known
    sector: str | None = None
    source: str = ""
    as_of: datetime | None = None  # vintage of this record


class CorporateActionKind(str, Enum):
    CASH_ACQUISITION = "CASH_ACQUISITION"
    DELISTING = "DELISTING"


@dataclass(frozen=True)
class CorporateAction:
    symbol: str
    kind: CorporateActionKind
    announced: date
    effective: date  # first day the shares no longer exist / trade
    cash_per_share: Decimal | None = None
    evidence: tuple[str, ...] = field(default_factory=tuple)  # filing ids / URLs


@runtime_checkable
class InstrumentMaster(Protocol):
    def get(self, symbol: str) -> InstrumentRecord | None: ...


@runtime_checkable
class CorporateActionSource(Protocol):
    def actions_for(self, symbol: str) -> Sequence[CorporateAction]: ...


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
    min_history_sessions: int = 60,
) -> TradabilityResult:
    """May ``intent`` be executed in ``symbol`` on the session ``session_day``?

    Rules, in order:
      1. The symbol must be well formed and known (no guessing from a stale quote).
      2. Not yet listed, delisted, acquired or halted on that session blocks every intent,
         including selling. A held name that disappears must be settled by a corporate-action
         cash-out (``settlements_due``), never by a simulated sale.
      3. Opening or adding is also blocked while a definitive cash deal is pending (price pinned,
         no upside) and while the listing is younger than ``min_history_sessions``.
    """
    try:
        sym = normalize_symbol(symbol)
    except InvalidSymbol as exc:
        return _blocked(TradabilityCode.INVALID_SYMBOL, str(exc))

    record = master.get(sym)
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
        evidence = tuple(a for act in actions.actions_for(sym) for a in act.evidence)
        return _blocked(code, f"{sym} not tradable on {session_day}; last traded {last}", evidence)

    if record.status is InstrumentStatus.HALTED:
        return _blocked(TradabilityCode.HALTED, f"{sym} is halted")

    if intent.adds_exposure:
        for act in actions.actions_for(sym):
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
    symbol: str
    shares: int
    cash: Decimal
    effective: date
    evidence: tuple[str, ...]


def settlements_due(
    holdings: dict[str, int],
    actions: CorporateActionSource,
    session_day: date,
) -> list[CashOut]:
    """Cash-out events for held names whose acquisition took effect on or before ``session_day``.

    The caller records them as ledger ``corporate_action`` events. Whole shares times the filed
    per-share price; nothing is estimated from a quote.
    """
    out: list[CashOut] = []
    for sym, shares in sorted(holdings.items()):
        if shares <= 0:
            continue
        for act in actions.actions_for(sym):
            if (
                act.kind is CorporateActionKind.CASH_ACQUISITION
                and act.cash_per_share is not None
                and act.effective <= session_day
            ):
                out.append(CashOut(sym, shares, act.cash_per_share * shares, act.effective, act.evidence))
    return out


class StaticInstrumentMaster:
    """In-memory master for tests and cached data."""

    def __init__(self, records: Sequence[InstrumentRecord]) -> None:
        self._records = {r.symbol: r for r in records}

    def get(self, symbol: str) -> InstrumentRecord | None:
        return self._records.get(symbol)


class StaticCorporateActions:
    def __init__(self, actions: Sequence[CorporateAction]) -> None:
        self._by_symbol: dict[str, list[CorporateAction]] = {}
        for a in actions:
            self._by_symbol.setdefault(a.symbol, []).append(a)

    def actions_for(self, symbol: str) -> Sequence[CorporateAction]:
        return tuple(self._by_symbol.get(symbol, ()))
