"""Pre-trade gate: the boundary the future ``advance(session T)`` loop calls.

Ports (``Protocol``s) describe what the loop must provide; the gate itself composes the pure
checks from ``market`` and ``risk`` and returns a decision with a stable reason code. It does
not place orders, touch a database, read a clock or call a model.

Three entry points map onto steps of the loop (doc 12 section 5):
  * ``queue_order``     step 8-9: a proposal decided at/after the close is queued for the next open
  * ``fill_at_open``    step 3:   the queued order meets the next session's official open
  * ``immediate_fill_allowed``    legacy guard: any caller that wants an instant fill is refused
                                  outside a regular session (defects E-1, E-2)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol

from the_reef.market.calendar import (
    CalendarRangeError,
    MarketCalendar,
    Session,
    TimePhase,
    classify,
    next_valid_open,
)
from the_reef.market.instruments import (
    CorporateActionSource,
    InstrumentMaster,
    Intent,
    InvalidSymbol,
    TradabilityCode,
    check_tradable,
    normalize_symbol,
)
from the_reef.market.quotes import Quote, QuoteIssue, validate_fill_quote
from the_reef.risk.engine import PortfolioView, RiskDecision, evaluate_entry, evaluate_exit
from the_reef.risk.limits import RiskLimits


class GateCode(str, Enum):
    ACCEPTED = "ACCEPTED"
    INVALID_SYMBOL = "INVALID_SYMBOL"
    CALENDAR_UNAVAILABLE = "CALENDAR_UNAVAILABLE"
    MARKET_CLOSED_WEEKEND = "MARKET_CLOSED_WEEKEND"
    MARKET_CLOSED_HOLIDAY = "MARKET_CLOSED_HOLIDAY"
    OUTSIDE_REGULAR_HOURS = "OUTSIDE_REGULAR_HOURS"
    INSTRUMENT_NOT_TRADABLE = "INSTRUMENT_NOT_TRADABLE"
    NO_VALID_OPEN_PRINT = "NO_VALID_OPEN_PRINT"
    RISK_REJECTED = "RISK_REJECTED"


@dataclass(frozen=True)
class OrderIntent:
    pod_id: str
    symbol: str
    intent: Intent
    decided_at: datetime  # timezone-aware
    ref_price: Decimal
    stop_price: Decimal | None  # required for open/add
    sector: str | None = None
    requested_shares: int | None = None  # allocator ceiling


@dataclass(frozen=True)
class QueuedOrder:
    intent: OrderIntent
    symbol: str  # normalized
    fill_session: date
    fill_not_before: datetime  # the open of the fill session


@dataclass(frozen=True)
class GateDecision:
    accepted: bool
    code: GateCode
    detail: str = ""
    queued: QueuedOrder | None = None
    shares: int = 0
    tradability: TradabilityCode | None = None
    quote_issues: tuple[QuoteIssue, ...] = ()
    risk: RiskDecision | None = None


class OpenPrintSource(Protocol):
    def official_open(self, symbol: str, session: Session) -> Quote | None: ...


@dataclass(frozen=True)
class GatePorts:
    """Everything the gate needs from the outside world. Injected; the loop owns the adapters."""

    calendar: MarketCalendar
    instruments: InstrumentMaster
    actions: CorporateActionSource
    limits: RiskLimits


def immediate_fill_allowed(ports: GatePorts, at: datetime) -> GateDecision:
    """Refuse an instant fill unless ``at`` is inside a regular session."""
    try:
        cls = classify(ports.calendar, at)
    except CalendarRangeError as exc:
        return GateDecision(False, GateCode.CALENDAR_UNAVAILABLE, str(exc))
    if cls.phase is TimePhase.REGULAR:
        return GateDecision(True, GateCode.ACCEPTED)
    code = {
        TimePhase.WEEKEND: GateCode.MARKET_CLOSED_WEEKEND,
        TimePhase.HOLIDAY: GateCode.MARKET_CLOSED_HOLIDAY,
    }.get(cls.phase, GateCode.OUTSIDE_REGULAR_HOURS)
    return GateDecision(False, code, f"{at.isoformat()} is {cls.phase.value}")


def queue_order(ports: GatePorts, order: OrderIntent) -> GateDecision:
    """Accept a decision for the next valid session open, or refuse it with a reason.

    Checked at decision time so an untradable name never reaches the queue; checked again
    at fill time because the instrument can change in between.
    """
    try:
        symbol = normalize_symbol(order.symbol)
    except InvalidSymbol as exc:
        return GateDecision(False, GateCode.INVALID_SYMBOL, str(exc))
    if order.intent.adds_exposure and order.stop_price is None:
        return GateDecision(False, GateCode.RISK_REJECTED, "open/add requires an invalidation price")
    try:
        fill = next_valid_open(ports.calendar, order.decided_at)
    except CalendarRangeError as exc:
        return GateDecision(False, GateCode.CALENDAR_UNAVAILABLE, str(exc))

    trade = check_tradable(
        symbol, fill.day, ports.instruments, ports.actions, ports.calendar,
        intent=order.intent, as_of=order.decided_at, min_history_sessions=ports.limits.min_history_sessions,
    )
    if not trade.ok:
        return GateDecision(False, GateCode.INSTRUMENT_NOT_TRADABLE, trade.detail, tradability=trade.code)
    queued = QueuedOrder(order, symbol, fill.day, fill.open)
    return GateDecision(True, GateCode.ACCEPTED, queued=queued, tradability=TradabilityCode.OK)


def fill_at_open(
    ports: GatePorts,
    queued: QueuedOrder,
    open_print: Quote | None,
    portfolio: PortfolioView,
    sleeve_cash: Decimal,
) -> GateDecision:
    """Resolve a queued order against the fill session's official open.

    The order is refused (not filled at a stale price) when the instrument is no longer
    tradable, the open print is missing or invalid, or Risk rejects it. The price is the
    open print itself, never a carried or cached price.
    """
    try:
        session = ports.calendar.session(queued.fill_session)
    except CalendarRangeError as exc:
        return GateDecision(False, GateCode.CALENDAR_UNAVAILABLE, str(exc))
    if session is None:
        return GateDecision(False, GateCode.MARKET_CLOSED_HOLIDAY, f"{queued.fill_session} is not a session")

    order = queued.intent
    trade = check_tradable(
        queued.symbol, queued.fill_session, ports.instruments, ports.actions, ports.calendar,
        intent=order.intent, as_of=queued.fill_not_before, min_history_sessions=ports.limits.min_history_sessions,
    )
    if not trade.ok:
        return GateDecision(False, GateCode.INSTRUMENT_NOT_TRADABLE, trade.detail, queued, tradability=trade.code)

    check = validate_fill_quote(open_print, symbol=queued.symbol, session=session)
    if not check.valid or open_print is None or open_print.price is None:
        return GateDecision(False, GateCode.NO_VALID_OPEN_PRINT, "no valid official open", queued, quote_issues=check.issues)

    if order.intent.adds_exposure:
        assert order.stop_price is not None
        risk = evaluate_entry(
            symbol=queued.symbol, sector=order.sector, ref_price=open_print.price, stop_price=order.stop_price,
            sleeve_cash=sleeve_cash, portfolio=portfolio, limits=ports.limits, requested_shares=order.requested_shares,
        )
    else:
        risk = evaluate_exit(
            symbol=queued.symbol, requested_shares=order.requested_shares or 0, portfolio=portfolio,
        )
    if not risk.approved:
        reasons = ",".join(r.value for r in risk.reasons)
        return GateDecision(False, GateCode.RISK_REJECTED, reasons, queued, risk=risk)
    return GateDecision(True, GateCode.ACCEPTED, queued=queued, shares=risk.shares, risk=risk,
                        tradability=TradabilityCode.OK)
