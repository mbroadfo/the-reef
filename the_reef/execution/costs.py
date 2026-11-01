"""Execution frictions folded into fill prices, so the ledger and its accounting stay unchanged.

Buys fill above the reference print and sells below it, by ``slippage_bps`` plus a per-share fee.
Stops that gap through the stop fill at the open and pay ``gap_slippage_bps`` on top: a stop becomes
a market order into a falling, thin market. The defaults are zero (frictionless), which is what
every existing test and the synthetic walkthrough use.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

D = Decimal
CENT = D("0.01")
BPS = D("10000")


@dataclass(frozen=True)
class ExecutionCosts:
    slippage_bps: Decimal = D("0")
    gap_slippage_bps: Decimal = D("0")  # extra, sells that gap through a stop only
    fee_per_share: Decimal = D("0")

    def buy_price(self, ref: Decimal) -> Decimal:
        if self == ExecutionCosts():
            return ref
        return (ref * (1 + self.slippage_bps / BPS) + self.fee_per_share).quantize(CENT, rounding=ROUND_CEILING)

    def sell_price(self, ref: Decimal, *, gap: bool = False) -> Decimal:
        if self == ExecutionCosts():
            return ref
        bps = self.slippage_bps + (self.gap_slippage_bps if gap else D("0"))
        return max(CENT, (ref * (1 - bps / BPS) - self.fee_per_share).quantize(CENT, rounding=ROUND_FLOOR))
