"""CrewAI tools that give Apex Shark access to The Tank."""
from __future__ import annotations

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional

from ..brokerage.the_tank import TheTank
from ..tools.market_data import get_price


_tank: Optional[TheTank] = None


def set_tank(tank: TheTank):
    global _tank
    _tank = tank


def get_tank() -> TheTank:
    global _tank
    if _tank is None:
        _tank = TheTank()
    return _tank


# ── tool input schemas ────────────────────────────────────────────────────────

class NoInput(BaseModel):
    pass


class BuyInput(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol")
    surfaced_by: str = Field(..., description="Which shark surfaced this opportunity")
    vetted_by: str = Field(..., description="Comma-separated list of analyst sharks who reviewed")
    conviction: int = Field(..., ge=1, le=10, description="Conviction score 1-10")
    stop_loss_pct: float = Field(default=7.0, description="Stop-loss percentage below entry (default 7%)")
    target_pct: float = Field(default=15.0, description="Target price percentage above entry (default 15%)")
    reason: str = Field(default="", description="Brief rationale for the trade")


class SellInput(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol to sell")
    reason: str = Field(default="", description="Reason for selling")


# ── tools ────────────────────────────────────────────────────────────────────

class GetPortfolioTool(BaseTool):
    name: str = "Get Portfolio State"
    description: str = (
        "Get current portfolio state: cash available, open positions, P&L, "
        "and recent trade history. Use this before making any trade decision."
    )
    args_schema: type[BaseModel] = NoInput

    def _run(self) -> str:
        return get_tank().summary()


class ExecuteBuyTool(BaseTool):
    name: str = "Execute Paper Buy"
    description: str = (
        "Execute a paper buy trade in The Tank. "
        "Do NOT specify shares — position size is calculated automatically from conviction (1-10) and available cash. "
        "Only whole shares are purchased (no fractional shares). "
        "Sets stop-loss and target automatically from percentages."
    )
    args_schema: type[BaseModel] = BuyInput

    def _run(
        self,
        ticker: str,
        surfaced_by: str,
        vetted_by: str,
        conviction: int,
        stop_loss_pct: float = 7.0,
        target_pct: float = 15.0,
        reason: str = "",
    ) -> str:
        tank = get_tank()
        price = get_price(ticker)
        if price is None:
            return f"Could not get current price for {ticker} — trade aborted"

        position_dollars = tank.max_position_size(conviction)
        shares = int(position_dollars / price)
        if shares < 1:
            return (
                f"TRADE SKIPPED: {ticker} @ ${price:.2f} — "
                f"conviction {conviction} allows ${position_dollars:.0f} but 1 share costs ${price:.2f}. "
                f"Raise conviction to at least {int((price / tank.portfolio_value() - 0.05) / 0.015) + 1} "
                f"or wait for a lower price."
            )

        stop_loss = round(price * (1 - stop_loss_pct / 100), 2)
        target = round(price * (1 + target_pct / 100), 2)

        ok, msg = tank.buy(
            ticker=ticker,
            shares=shares,
            price=price,
            surfaced_by=surfaced_by,
            vetted_by=vetted_by,
            conviction=conviction,
            stop_loss=stop_loss,
            target_price=target,
            reason=reason,
        )
        return msg


class ExecuteSellTool(BaseTool):
    name: str = "Execute Paper Sell"
    description: str = (
        "Sell all shares of a position in The Tank. "
        "Use when exiting a position due to target hit, stop-loss, or changed thesis."
    )
    args_schema: type[BaseModel] = SellInput

    def _run(self, ticker: str, reason: str = "") -> str:
        tank = get_tank()
        positions = tank.positions
        if ticker not in positions:
            return f"No open position in {ticker}"

        pos = positions[ticker]
        price = get_price(ticker)
        if price is None:
            return f"Could not get current price for {ticker} — sell aborted"

        ok, msg = tank.sell(ticker=ticker, shares=pos.shares, price=price, reason=reason)
        return msg


class CheckStopLossesTool(BaseTool):
    name: str = "Check Stop Losses"
    description: str = (
        "Check all open positions against their stop-loss levels using current prices. "
        "Returns list of positions that need to be exited."
    )
    args_schema: type[BaseModel] = NoInput

    def _run(self) -> str:
        tank = get_tank()
        # Refresh prices first
        positions = tank.positions
        if not positions:
            return "No open positions."

        prices = {ticker: get_price(ticker) for ticker in positions}
        tank.update_prices({t: p for t, p in prices.items() if p is not None})

        triggered = tank.check_stop_losses()
        if not triggered:
            return "No stop-losses triggered. All positions within bounds."

        msgs = []
        for ticker, price in triggered:
            pos = positions[ticker]
            msgs.append(
                f"{ticker} STOP-LOSS TRIGGERED: "
                f"current ${price:.2f} <= stop ${pos.stop_loss:.2f} | "
                f"P&L {pos.unrealized_pnl_pct:+.1f}%"
            )
        return "\n".join(msgs)
