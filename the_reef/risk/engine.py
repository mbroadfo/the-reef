"""Deterministic Risk Engine: pure functions, no I/O, no clock, no randomness.

Semantics (doc 19, D8a-D8f):
  * Pauses (daily loss, drawdown, untrusted book) block new opens and adds. Exits are never blocked.
  * Limits clamp a request down. A clamp is recorded and never redistributes capital elsewhere.
  * The smaller of the sizing rules wins: risk per trade, single-position cap, sleeve cash.
  * Nothing here can raise a size above the request or above any limit.
Every decision carries the reasons and clamp events so it can be audited and tested.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, Decimal
from enum import Enum
from typing import Mapping, Sequence

from the_reef.risk.limits import RiskLimits

D = Decimal
UNKNOWN_SECTOR = "UNKNOWN"


class RejectCode(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_STOP = "INVALID_STOP"
    BOOK_UNTRUSTED = "BOOK_UNTRUSTED"
    DAILY_LOSS_PAUSE = "DAILY_LOSS_PAUSE"
    DRAWDOWN_PAUSE = "DRAWDOWN_PAUSE"
    POSITION_AT_CAP = "POSITION_AT_CAP"
    SECTOR_CAP = "SECTOR_CAP"
    MAX_INVESTED = "MAX_INVESTED"
    NO_CASH = "NO_CASH"
    SIZE_ZERO = "SIZE_ZERO"
    NOT_HELD = "NOT_HELD"
    RISK_BUDGET_EXHAUSTED = "RISK_BUDGET_EXHAUSTED"


class Rule(str, Enum):
    RISK_PER_TRADE = "RISK_PER_TRADE"
    POSITION_CAP = "POSITION_CAP"
    SLEEVE_CASH = "SLEEVE_CASH"
    FUND_CASH = "FUND_CASH"
    SECTOR_CAP = "SECTOR_CAP"
    MAX_INVESTED = "MAX_INVESTED"
    ALLOCATOR_CEILING = "ALLOCATOR_CEILING"
    HOLDING = "HOLDING"


@dataclass(frozen=True)
class PositionView:
    symbol: str
    shares: int
    price: Decimal  # valid mark
    sector: str | None = None
    stop_price: Decimal | None = None  # the position's invalidation price; None = unknown

    @property
    def value(self) -> Decimal:
        return self.price * self.shares

    @property
    def stop_risk(self) -> Decimal:
        """Loss if the stop is hit from the current mark. An unknown stop is counted as a total
        loss (conservative), so a position without a recorded stop cannot be added to."""
        if self.stop_price is None:
            return self.value
        return max(self.price - self.stop_price, D("0")) * self.shares


@dataclass(frozen=True)
class PortfolioView:
    nav: Decimal
    cash: Decimal
    prior_close_nav: Decimal
    high_water_mark: Decimal
    positions: tuple[PositionView, ...] = ()
    book_trusted: bool = True

    @property
    def invested(self) -> Decimal:
        return sum((p.value for p in self.positions), D("0"))

    def value_of(self, symbol: str) -> Decimal:
        return sum((p.value for p in self.positions if p.symbol == symbol), D("0"))

    def shares_of(self, symbol: str) -> int:
        return sum(p.shares for p in self.positions if p.symbol == symbol)

    def stop_risk_of(self, symbol: str) -> Decimal:
        """Stop-risk already carried in ``symbol`` across all its lots."""
        return sum((p.stop_risk for p in self.positions if p.symbol == symbol), D("0"))

    def sector_value(self, sector: str | None) -> Decimal:
        key = sector or UNKNOWN_SECTOR
        return sum((p.value for p in self.positions if (p.sector or UNKNOWN_SECTOR) == key), D("0"))


@dataclass(frozen=True)
class ClampEvent:
    rule: Rule
    requested_shares: int
    allowed_shares: int
    detail: str = ""


@dataclass(frozen=True)
class Sizing:
    shares: int
    binding: Rule
    by_risk: Decimal
    by_cap: Decimal
    by_cash: Decimal


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    shares: int
    reasons: tuple[RejectCode, ...] = ()
    clamps: tuple[ClampEvent, ...] = ()
    flags: tuple[str, ...] = field(default_factory=tuple)


def _floor(x: Decimal) -> int:
    return int(x.to_integral_value(rounding=ROUND_FLOOR))


# --- state tests ---------------------------------------------------------------------------

def daily_loss_paused(nav: Decimal, prior_close_nav: Decimal, limits: RiskLimits) -> bool:
    """True when NAV is down at least ``daily_loss_pause_pct`` against the prior close."""
    if prior_close_nav <= 0:
        return False
    return (prior_close_nav - nav) / prior_close_nav >= limits.daily_loss_pause_pct


def drawdown_paused(nav: Decimal, high_water_mark: Decimal, limits: RiskLimits) -> bool:
    """True when NAV is down at least ``drawdown_pause_pct`` from the high-water mark.

    Resuming is a human action recorded elsewhere; this function only reports the state.
    """
    if high_water_mark <= 0:
        return False
    return (high_water_mark - nav) / high_water_mark >= limits.drawdown_pause_pct


def pause_reasons(portfolio: PortfolioView, limits: RiskLimits) -> tuple[RejectCode, ...]:
    reasons: list[RejectCode] = []
    if not portfolio.book_trusted:
        reasons.append(RejectCode.BOOK_UNTRUSTED)
    if daily_loss_paused(portfolio.nav, portfolio.prior_close_nav, limits):
        reasons.append(RejectCode.DAILY_LOSS_PAUSE)
    if drawdown_paused(portfolio.nav, portfolio.high_water_mark, limits):
        reasons.append(RejectCode.DRAWDOWN_PAUSE)
    return tuple(reasons)


# --- sizing --------------------------------------------------------------------------------

def size_order(
    *,
    nav: Decimal,
    ref_price: Decimal,
    stop_price: Decimal,
    sleeve_cash: Decimal,
    limits: RiskLimits,
    existing_risk: Decimal = D("0"),
) -> Sizing | None:
    """shares = floor(min((risk_pct*NAV - existing_risk)/(ref-stop), cap_pct*NAV/ref, sleeve_cash/ref)).

    ``existing_risk`` is the stop-risk already carried in the same name: the per-trade risk
    budget applies to the position as a whole, so each add only gets what is left of it.

    Returns None for an invalid request (non-positive NAV/price, stop at or above reference).
    """
    if nav <= 0 or ref_price <= 0 or stop_price <= 0 or stop_price >= ref_price or sleeve_cash < 0:
        return None
    by_risk = (limits.risk_per_trade_pct * nav - existing_risk) / (ref_price - stop_price)
    if by_risk < 0:
        by_risk = D("0")
    by_cap = limits.max_position_pct * nav / ref_price
    by_cash = sleeve_cash / ref_price
    smallest = min(by_risk, by_cap, by_cash)
    if smallest == by_risk:
        binding = Rule.RISK_PER_TRADE
    elif smallest == by_cap:
        binding = Rule.POSITION_CAP
    else:
        binding = Rule.SLEEVE_CASH
    return Sizing(_floor(smallest), binding, by_risk, by_cap, by_cash)


# --- decisions -----------------------------------------------------------------------------

def evaluate_entry(
    *,
    symbol: str,
    sector: str | None,
    ref_price: Decimal,
    stop_price: Decimal,
    sleeve_cash: Decimal,
    portfolio: PortfolioView,
    limits: RiskLimits,
    requested_shares: int | None = None,
) -> RiskDecision:
    """Decide an open or add. ``requested_shares`` (the allocator's ceiling) can only be lowered."""
    flags: list[str] = []
    if ref_price <= 0 or stop_price <= 0 or portfolio.nav <= 0:
        return RiskDecision(False, 0, (RejectCode.INVALID_REQUEST,))
    if stop_price >= ref_price:
        return RiskDecision(False, 0, (RejectCode.INVALID_STOP,))

    paused = pause_reasons(portfolio, limits)
    if paused:
        return RiskDecision(False, 0, paused)

    existing_value = portfolio.value_of(symbol)
    nav = portfolio.nav
    if existing_value >= limits.max_position_pct * nav:
        return RiskDecision(False, 0, (RejectCode.POSITION_AT_CAP,), flags=("POSITION_OVER_CAP_NO_ADDS",))

    existing_risk = portfolio.stop_risk_of(symbol)
    if existing_risk >= limits.risk_per_trade_pct * nav:
        return RiskDecision(False, 0, (RejectCode.RISK_BUDGET_EXHAUSTED,), flags=("POSITION_RISK_AT_BUDGET",))

    sizing = size_order(
        nav=nav, ref_price=ref_price, stop_price=stop_price, sleeve_cash=sleeve_cash, limits=limits,
        existing_risk=existing_risk,
    )
    if sizing is None:
        return RiskDecision(False, 0, (RejectCode.INVALID_REQUEST,))

    # An add counts the shares already held against the single-position cap.
    cap_room = _floor((limits.max_position_pct * nav - existing_value) / ref_price)
    shares = min(sizing.shares, cap_room)
    clamps: list[ClampEvent] = []
    if cap_room < sizing.shares:
        clamps.append(ClampEvent(Rule.POSITION_CAP, sizing.shares, cap_room, "existing holding counted"))

    if requested_shares is not None:
        if requested_shares < 0:
            return RiskDecision(False, 0, (RejectCode.INVALID_REQUEST,))
        if requested_shares < shares:
            clamps.append(ClampEvent(Rule.ALLOCATOR_CEILING, shares, requested_shares, "allocator ceiling"))
            shares = requested_shares

    def clamp(rule: Rule, room: int, detail: str) -> None:
        nonlocal shares
        room = max(room, 0)
        if room < shares:
            clamps.append(ClampEvent(rule, shares, room, detail))
            shares = room

    clamp(Rule.FUND_CASH, _floor(portfolio.cash / ref_price), "fund cash")
    clamp(
        Rule.MAX_INVESTED,
        _floor((limits.max_invested_pct * nav - portfolio.invested) / ref_price),
        f"max invested {limits.max_invested_pct:.0%}",
    )
    sector_limit = limits.max_unknown_sector_pct if (sector or UNKNOWN_SECTOR) == UNKNOWN_SECTOR else limits.max_sector_pct
    clamp(
        Rule.SECTOR_CAP,
        _floor((sector_limit * nav - portfolio.sector_value(sector)) / ref_price),
        f"sector {sector or UNKNOWN_SECTOR} cap {sector_limit:.0%}",
    )

    if shares <= 0:
        if sizing.shares <= 0:
            code = RejectCode.NO_CASH if sizing.binding is Rule.SLEEVE_CASH else RejectCode.SIZE_ZERO
            return RiskDecision(False, 0, (code,), tuple(clamps))
        code = _reject_code_for(clamps)
        return RiskDecision(False, 0, (code,), tuple(clamps))
    return RiskDecision(True, shares, (), tuple(clamps), tuple(flags))


def _reject_code_for(clamps: Sequence[ClampEvent]) -> RejectCode:
    last = clamps[-1].rule if clamps else Rule.RISK_PER_TRADE
    return {
        Rule.SECTOR_CAP: RejectCode.SECTOR_CAP,
        Rule.MAX_INVESTED: RejectCode.MAX_INVESTED,
        Rule.FUND_CASH: RejectCode.NO_CASH,
        Rule.POSITION_CAP: RejectCode.POSITION_AT_CAP,
    }.get(last, RejectCode.SIZE_ZERO)


def evaluate_exit(*, symbol: str, requested_shares: int, portfolio: PortfolioView) -> RiskDecision:
    """Reduce or close. Never paused, never blocked by an untrusted book; capped at shares held."""
    held = portfolio.shares_of(symbol)
    if requested_shares <= 0:
        return RiskDecision(False, 0, (RejectCode.INVALID_REQUEST,))
    if held <= 0:
        return RiskDecision(False, 0, (RejectCode.NOT_HELD,))
    shares = min(requested_shares, held)
    clamps: tuple[ClampEvent, ...] = ()
    if shares < requested_shares:
        clamps = (ClampEvent(Rule.HOLDING, requested_shares, shares, "cannot sell more than held"),)
    return RiskDecision(True, shares, (), clamps)


def sector_exposure(portfolio: PortfolioView) -> Mapping[str, Decimal]:
    """Fraction of NAV per sector (UNKNOWN for unmapped names)."""
    out: dict[str, Decimal] = {}
    if portfolio.nav <= 0:
        return out
    for p in portfolio.positions:
        key = p.sector or UNKNOWN_SECTOR
        out[key] = out.get(key, D("0")) + p.value / portfolio.nav
    return out
