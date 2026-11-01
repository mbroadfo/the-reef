"""Research agents: the extensible internal-research interface of a shark pod.

A pod's research desk is a list of agents. Each reads only point-in-time bars (and, later, any
other point-in-time source) and returns a ``Finding`` for a ticker: a verdict, a sentence, and the
figures behind it. The agents here are deterministic and use no model. An LLM-backed agent would
implement the same ``analyze`` and return the same ``Finding``; the shared budget and the engine
stay outside the pod. (Pattern: specialist research roles feeding a decision, as in TradingAgents
and ai-hedge-fund; see docs/reef2-aquarium.md.)
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Sequence

from the_reef.market.bars import DailyBar
from the_reef.strategy.base import Finding
from the_reef.strategy.hunter import atr, sma

D = Decimal


class ResearchAgent(Protocol):
    agent_id: str
    role: str

    def analyze(self, symbol: str, bars: Sequence[DailyBar]) -> Finding | None: ...


def _f(x: Decimal, nd: int = 2) -> str:
    return f"{x:.{nd}f}"


def _pct(x: Decimal) -> str:
    return f"{x * 100:+.1f}%"


@dataclass(frozen=True)
class BreakoutScout:
    lookback: int = 20
    agent_id: str = "breakout-scout"
    role: str = "Technical scout"

    def analyze(self, symbol: str, bars: Sequence[DailyBar]) -> Finding | None:
        if len(bars) < self.lookback + 1:
            return None
        closes = [b.close for b in bars]
        prior_high, close = max(closes[-self.lookback - 1:-1]), closes[-1]
        margin = close / prior_high - 1
        return Finding(self.agent_id, self.role, "support" if close > prior_high else "oppose",
                       f"Closed {_pct(margin)} above its {self.lookback}-session closing high.",
                       (("Close", _f(close)), (f"{self.lookback}d closing high", _f(prior_high)), ("Margin", _pct(margin))))


@dataclass(frozen=True)
class TrendFilter:
    lookback: int = 50
    agent_id: str = "trend-filter"
    role: str = "Trend analyst"

    def analyze(self, symbol: str, bars: Sequence[DailyBar]) -> Finding | None:
        if len(bars) < self.lookback:
            return None
        closes = [b.close for b in bars]
        avg, close = sma(closes, self.lookback), closes[-1]
        gap = close / avg - 1
        return Finding(self.agent_id, self.role, "support" if close > avg else "oppose",
                       f"Price is {_pct(gap)} versus its {self.lookback}-session average.",
                       ((f"SMA{self.lookback}", _f(avg)), ("Close vs SMA", _pct(gap))))


@dataclass(frozen=True)
class LiquidityCheck:
    window: int = 20
    minimum: Decimal = D("1000000")
    agent_id: str = "liquidity-check"
    role: str = "Market-structure analyst"

    def analyze(self, symbol: str, bars: Sequence[DailyBar]) -> Finding | None:
        if len(bars) < self.window:
            return None
        dv = sum((b.close * b.volume for b in bars[-self.window:]), D("0")) / self.window
        return Finding(self.agent_id, self.role, "support" if dv >= self.minimum else "oppose",
                       f"Trades about ${dv:,.0f} a day, floor ${self.minimum:,.0f}.",
                       ((f"Avg {self.window}d dollar volume", f"${dv:,.0f}"),))


@dataclass(frozen=True)
class OversoldScout:
    lookback: int = 20
    entry_z: Decimal = D("-1.7")
    agent_id: str = "oversold-scout"
    role: str = "Contrarian scout"

    def analyze(self, symbol: str, bars: Sequence[DailyBar]) -> Finding | None:
        z = oversold_z(bars, self.lookback)
        if z is None:
            return None
        closes = [b.close for b in bars]
        drop5 = closes[-1] / closes[-6] - 1
        return Finding(self.agent_id, self.role, "support" if z <= self.entry_z else "neutral",
                       f"Stretched {abs(z):.1f} standard deviations below its {self.lookback}-session mean after a {_pct(drop5)} five-session move.",
                       (("Z-score", _f(z)), (f"SMA{self.lookback}", _f(sma(closes, self.lookback))), ("5-session move", _pct(drop5))))


@dataclass(frozen=True)
class VolatilityStop:
    period: int = 14
    mult: Decimal = D("2")
    agent_id: str = "volatility-stop"
    role: str = "Risk scout"

    def analyze(self, symbol: str, bars: Sequence[DailyBar]) -> Finding | None:
        a = atr(bars, self.period)
        if a is None:
            return None
        close = bars[-1].close
        dist = self.mult * a / close
        return Finding(self.agent_id, self.role, "neutral",
                       f"ATR{self.period} is {_f(a)} ({a / close * 100:.1f}% of price); a {self.mult}x ATR stop risks {dist * 100:.1f}%.",
                       ((f"ATR{self.period}", _f(a)), ("Stop distance", _pct(-dist))))


def oversold_z(bars: Sequence[DailyBar], lookback: int) -> Decimal | None:
    """(close - mean) / population stdev of the last ``lookback`` closes; None when flat or short."""
    if len(bars) < lookback:
        return None
    window = [b.close for b in bars[-lookback:]]
    mean = sum(window, D("0")) / lookback
    var = sum(((c - mean) ** 2 for c in window), D("0")) / lookback
    if var == 0:
        return None
    return (window[-1] - mean) / var.sqrt()


@dataclass(frozen=True)
class ResearchDesk:
    agents: tuple[ResearchAgent, ...]

    def run(self, symbol: str, bars: Sequence[DailyBar]) -> tuple[Finding, ...]:
        out = []
        for a in self.agents:
            f = a.analyze(symbol, bars)
            if f is not None:
                out.append(f)
        return tuple(out)
