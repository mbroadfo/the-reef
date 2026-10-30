"""Hunter: a deterministic daily-bar momentum breakout strategy (no LLM, no randomness).

Rules, evaluated on the close of session T using only bars that had closed by then:

ENTRY (all must hold)
  1. Breakout: close[T] is above the highest close of the previous ``breakout_lookback`` (20) sessions.
  2. Trend: close[T] is above the simple average of the last ``trend_lookback`` (50) closes.
  3. Liquidity: the average of close x volume over the last 20 sessions is at least ``min_dollar_volume``.
  4. Enough history: at least ``trend_lookback + 1`` bars.
  5. Not already held in this sleeve and no order pending for it (no pyramiding in v1).
  Candidates are ranked by 20-session rate of change; at most ``max_candidates`` are proposed.
  The proposal carries ``stop = close - stop_atr_mult x ATR(atr_period)`` rounded down to a cent.

EXIT (for holdings, same close)
  * Trend break: close[T] is below the simple average of the last ``exit_lookback`` (20) closes
    -> propose CLOSE (executes at the next valid open).
  * Trailing stop: the stop may only rise, to close - stop_atr_mult x ATR, never above the close.
  * The initial and trailing stops are resting stop orders simulated by the engine against each
    session's open and low (gap-aware), independent of this class.

Everything is Decimal. ATR uses the simple average of true range over ``atr_period`` sessions.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from typing import Sequence

from the_reef.market.bars import DailyBar
from the_reef.market.instruments import Intent
from the_reef.strategy.base import Proposal, Review, StrategyContext, spec_hash

D = Decimal
CENT = D("0.01")


@dataclass(frozen=True)
class HunterParams:
    breakout_lookback: int = 20
    trend_lookback: int = 50
    exit_lookback: int = 20
    atr_period: int = 14
    stop_atr_mult: Decimal = D("2")
    min_dollar_volume: Decimal = D("1000000")
    max_candidates: int = 2


def sma(values: Sequence[Decimal], n: int) -> Decimal:
    window = values[-n:]
    return sum(window, D("0")) / len(window)


def atr(bars: Sequence[DailyBar], period: int) -> Decimal | None:
    if len(bars) < period + 1:
        return None
    trs = []
    for prev, cur in zip(bars[-period - 1:-1], bars[-period:]):
        trs.append(max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close)))
    return sum(trs, D("0")) / period


def floor_cent(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_FLOOR)


class Hunter:
    strategy_id = "hunter-momentum"
    version = "1"

    def __init__(self, params: HunterParams | None = None) -> None:
        self.params = params or HunterParams()

    @property
    def spec_hash(self) -> str:
        return spec_hash(self.strategy_id, self.version, self.params.__dict__)

    # -- entries ---------------------------------------------------------------------------
    def propose(self, ctx: StrategyContext) -> list[Proposal]:
        p = self.params
        found: list[Proposal] = []
        for symbol, bars in sorted(ctx.bars.items()):
            if symbol in ctx.holdings or symbol in ctx.blocked or len(bars) < p.trend_lookback + 1:
                continue
            closes = [b.close for b in bars]
            close = closes[-1]
            prior_high = max(closes[-p.breakout_lookback - 1:-1])
            trend = sma(closes, p.trend_lookback)
            dollar_vol = sum((b.close * b.volume for b in bars[-20:]), D("0")) / 20
            a = atr(bars, p.atr_period)
            if a is None or close <= prior_high or close <= trend or dollar_vol < p.min_dollar_volume:
                continue
            stop = floor_cent(close - p.stop_atr_mult * a)
            if stop <= 0 or stop >= close:
                continue
            roc = close / closes[-21] - 1
            found.append(Proposal(
                symbol, Intent.OPEN, roc, close, stop,
                f"breakout: close {close} > 20d high {prior_high}; > SMA50 {trend:.2f}; ROC20 {roc:.4f}; "
                f"ATR14 {a:.4f}; stop {stop}",
            ))
        found.sort(key=lambda x: (-x.score, x.symbol))
        return found[: p.max_candidates]

    # -- holdings --------------------------------------------------------------------------
    def review(self, ctx: StrategyContext) -> Review:
        p = self.params
        exits: list[Proposal] = []
        stops: dict[str, Decimal] = {}
        for symbol, hold in sorted(ctx.holdings.items()):
            bars = ctx.bars.get(symbol, ())
            if len(bars) < max(p.exit_lookback, p.atr_period + 1):
                continue
            closes = [b.close for b in bars]
            close = closes[-1]
            if close < sma(closes, p.exit_lookback):
                exits.append(Proposal(
                    symbol, Intent.CLOSE, D("0"), close, None,
                    f"trend break: close {close} < SMA{p.exit_lookback} {sma(closes, p.exit_lookback):.2f}",
                ))
                continue
            a = atr(bars, p.atr_period)
            if a is not None:
                trail = floor_cent(close - p.stop_atr_mult * a)
                if 0 < trail < close and (hold.stop_price is None or trail > hold.stop_price):
                    stops[symbol] = trail
        return Review(tuple(exits), stops)
