"""Execution frictions folded into fill prices, so the ledger and its accounting stay unchanged.

Buys fill above the reference print and sells below it, by ``slippage_bps`` plus a per-share fee. The fee is
added exactly (a half-cent fee stays a half cent per share); only the slippage is rounded, against the trader.
Stops that gap through the stop fill at the open and pay ``gap_slippage_bps`` on top: a stop becomes
a market order into a falling, thin market. The defaults are zero (frictionless), which is what
every existing test and the synthetic walkthrough use.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

D = Decimal
TICK = D("0.000001")  # slippage is rounded against the trader to a millionth of a dollar; fees are never rounded
BPS = D("10000")


@dataclass(frozen=True)
class ExecutionCosts:
    slippage_bps: Decimal = D("0")
    gap_slippage_bps: Decimal = D("0")  # extra, sells that gap through a stop only
    fee_per_share: Decimal = D("0")

    def buy_price(self, ref: Decimal) -> Decimal:
        if self == ExecutionCosts():
            return ref
        return (ref * (1 + self.slippage_bps / BPS)).quantize(TICK, rounding=ROUND_CEILING) + self.fee_per_share

    def sell_price(self, ref: Decimal, *, gap: bool = False) -> Decimal:
        if self == ExecutionCosts():
            return ref
        bps = self.slippage_bps + (self.gap_slippage_bps if gap else D("0"))
        return max(TICK, (ref * (1 - bps / BPS)).quantize(TICK, rounding=ROUND_FLOOR) - self.fee_per_share)
