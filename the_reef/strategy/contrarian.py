"""Contrarian: a deterministic daily-bar mean-reversion strategy (no LLM, no randomness).

The opposite bet to Hunter's: it buys fear inside an uptrend instead of strength.

ENTRY (evaluated on the close of session T, point-in-time bars only; all must hold)
  1. Oversold: close is at least ``entry_z`` standard deviations below the ``lookback``-session mean.
  2. Uptrend intact: close is above the ``trend_lookback`` (50) session average.
  3. Liquidity: average 20-session dollar volume at least ``min_dollar_volume``.
  4. Not held in this sleeve and no order pending (no pyramiding).
  Ranked by most negative z; at most ``max_candidates`` proposed. Stop = close - ``stop_atr_mult`` x ATR14,
  fixed (it never rises, unlike Hunter's trail), rounded down to a cent.

EXIT
  * Reversion done: close is back at or above the ``lookback``-session mean -> propose CLOSE.
  * The resting stop is simulated by the engine against each session's open and low.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from the_reef.market.instruments import Intent
from the_reef.pods.research import oversold_z
from the_reef.strategy.base import Proposal, Review, StrategyContext, spec_hash
from the_reef.strategy.hunter import atr, floor_cent, sma

D = Decimal


@dataclass(frozen=True)
class ContrarianParams:
    lookback: int = 20
    entry_z: Decimal = D("-1.7")
    trend_lookback: int = 50
    atr_period: int = 14
    stop_atr_mult: Decimal = D("2.5")
    min_dollar_volume: Decimal = D("1000000")
    max_candidates: int = 2


class Contrarian:
    strategy_id = "contrarian-reversion"
    version = "1"

    def __init__(self, params: ContrarianParams | None = None) -> None:
        self.params = params or ContrarianParams()

    @property
    def spec_hash(self) -> str:
        return spec_hash(self.strategy_id, self.version, self.params.__dict__)

    def propose(self, ctx: StrategyContext) -> list[Proposal]:
        p = self.params
        found: list[Proposal] = []
        for symbol, bars in sorted(ctx.bars.items()):
            if symbol in ctx.holdings or symbol in ctx.blocked or len(bars) < p.trend_lookback + 1:
                continue
            closes = [b.close for b in bars]
            close = closes[-1]
            z = oversold_z(bars, p.lookback)
            a = atr(bars, p.atr_period)
            dollar_vol = sum((b.close * b.volume for b in bars[-20:]), D("0")) / 20
            if z is None or a is None or z > p.entry_z or close <= sma(closes, p.trend_lookback) \
                    or dollar_vol < p.min_dollar_volume:
                continue
            stop = floor_cent(close - p.stop_atr_mult * a)
            if stop <= 0 or stop >= close:
                continue
            found.append(Proposal(
                symbol, Intent.OPEN, -z, close, stop,
                f"oversold: z {z:.2f} <= {p.entry_z}; close {close} > SMA{p.trend_lookback} {sma(closes, p.trend_lookback):.2f}; "
                f"ATR14 {a:.4f}; stop {stop}",
            ))
        found.sort(key=lambda x: (-x.score, x.symbol))
        return found[: p.max_candidates]

    def review(self, ctx: StrategyContext) -> Review:
        p = self.params
        exits: list[Proposal] = []
        for symbol in sorted(ctx.holdings):
            bars = ctx.bars.get(symbol, ())
            if len(bars) < p.lookback:
                continue
            closes = [b.close for b in bars]
            mean = sma(closes, p.lookback)
            if closes[-1] >= mean:
                exits.append(Proposal(symbol, Intent.CLOSE, D("0"), closes[-1], None,
                                      f"reversion complete: close {closes[-1]} >= SMA{p.lookback} {mean:.2f}"))
        return Review(tuple(exits), {})
