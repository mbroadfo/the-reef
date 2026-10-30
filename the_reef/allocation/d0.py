"""D0: the deterministic allocator (decision D21). No model calls, no randomness.

D0 does two things, both pure:
  * ``sleeve_targets``: split fund NAV among sleeves by fixed weights (funding at epoch start).
  * ``allocate``: given a sleeve's ranked entry proposals, cap each at an equal share of the
    sleeve's cash among the proposals taken, and take at most ``max_new_per_session``.

D0 only produces a share *ceiling*. The Risk Engine remains the authority and can only lower it
(position cap, 0.5% risk per trade, sector, invested, cash). Apex judgment and the D1-D3 shadow
arms are not implemented here.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from typing import Mapping, Sequence

from the_reef.strategy.base import Proposal

D = Decimal


@dataclass(frozen=True)
class D0Config:
    sleeve_weights: Mapping[str, Decimal]  # fraction of fund NAV per sleeve; the rest stays unallocated
    max_new_per_session: int = 2

    def __post_init__(self) -> None:
        total = sum(self.sleeve_weights.values(), D("0"))
        if any(w <= 0 for w in self.sleeve_weights.values()) or total > 1:
            raise ValueError("sleeve weights must be positive and sum to at most 1")
        if self.max_new_per_session < 1:
            raise ValueError("max_new_per_session must be >= 1")


@dataclass(frozen=True)
class Allocation:
    proposal: Proposal
    ceiling_shares: int


def sleeve_targets(nav: Decimal, config: D0Config) -> dict[str, Decimal]:
    return {sid: (nav * w).quantize(D("0.01"), rounding=ROUND_FLOOR) for sid, w in sorted(config.sleeve_weights.items())}


def allocate(proposals: Sequence[Proposal], sleeve_cash: Decimal, config: D0Config) -> list[Allocation]:
    ranked = sorted(proposals, key=lambda p: (-p.score, p.symbol))[: config.max_new_per_session]
    if not ranked or sleeve_cash <= 0:
        return []
    share_of_cash = sleeve_cash / len(ranked)
    out = []
    for p in ranked:
        ceiling = int((share_of_cash / p.ref_price).to_integral_value(rounding=ROUND_FLOOR))
        out.append(Allocation(p, ceiling))
    return out
