"""The six shark pods: registration, mandates, and an honest active/inactive status.

A pod is a mandate (investment philosophy), a research desk, a strategy and a virtual capital sleeve.
Only pods with a working deterministic strategy are ACTIVE and funded; the rest are registered with
their mandate and say what they are missing. Nothing here invents activity for an inactive pod.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum
from typing import Callable

from the_reef.pods.research import (
    BreakoutScout,
    LiquidityCheck,
    OversoldScout,
    ResearchDesk,
    TrendFilter,
    VolatilityStop,
)
from the_reef.strategy.base import Proposal, Review, Strategy, StrategyContext
from the_reef.strategy.contrarian import Contrarian
from the_reef.strategy.hunter import Hunter

D = Decimal


class PodStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


@dataclass(frozen=True)
class PodSpec:
    pod_id: str
    name: str
    tagline: str
    mandate: str
    color: str  # a CSS variable already defined by the dashboard theme
    status: PodStatus
    sleeve_weight: Decimal  # D0 fixed weight of fund NAV; inactive pods get none
    inactive_reason: str = ""
    research_agents: tuple[str, ...] = ()
    make_strategy: Callable[[], Strategy] | None = None


class PodStrategy:
    """Adds a thesis and the research desk's findings to any strategy's proposals, and carries the
    pod's capital-request and exit-plan declarations. The wrapped strategy is not modified."""

    def __init__(self, base: Strategy, desk: ResearchDesk, thesis: Callable[[str, tuple], str],
                 request_fraction: Decimal, exit_rules: tuple[str, ...]) -> None:
        self.base, self.desk, self._thesis = base, desk, thesis
        self.request_fraction, self.exit_rules = request_fraction, exit_rules
        self.strategy_id = base.strategy_id

    @property
    def spec_hash(self) -> str:
        return self.base.spec_hash

    def propose(self, ctx: StrategyContext) -> list[Proposal]:
        out = []
        for p in self.base.propose(ctx):
            findings = self.desk.run(p.symbol, ctx.bars[p.symbol])
            out.append(replace(p, thesis=self._thesis(p.symbol, findings), findings=findings))
        return out

    def review(self, ctx: StrategyContext) -> Review:
        return self.base.review(ctx)


def _momentum() -> Strategy:
    desk = ResearchDesk((BreakoutScout(), TrendFilter(), LiquidityCheck(), VolatilityStop(mult=D("2"))))
    return PodStrategy(
        Hunter(), desk,
        lambda sym, f: f"{sym} just broke out to a new 20-session closing high above its 50-session trend. "
                       "Momentum tends to persist, so Momentum buys the continuation and lets a volatility stop define the risk.",
        D("0.5"),
        ("Exit on a close below the 20-session average", "Trailing stop at 2 x ATR14, only ever raised"))


def _contrarian() -> Strategy:
    desk = ResearchDesk((OversoldScout(), TrendFilter(), LiquidityCheck(), VolatilityStop(mult=D("2.5"))))
    return PodStrategy(
        Contrarian(), desk,
        lambda sym, f: f"{sym} has been sold hard, well under its 20-session mean, while its 50-session "
                       "uptrend still holds. Contrarian buys the fear and expects a return to the mean.",
        D("0.5"),
        ("Exit when the close is back at the 20-session average", "Fixed stop at 2.5 x ATR14, never raised"))


POD_REGISTRY: tuple[PodSpec, ...] = (
    PodSpec("momentum", "Momentum", "Buys strength", "Trend-following breakouts in liquid names, held while the trend lasts.",
            "var(--shark-momentum)", PodStatus.ACTIVE, D("0.30"),
            research_agents=("breakout-scout", "trend-filter", "liquidity-check", "volatility-stop"), make_strategy=_momentum),
    PodSpec("contrarian", "Contrarian", "Buys fear", "Mean-reversion entries in oversold names inside an intact uptrend.",
            "var(--shark-contrarian)", PodStatus.ACTIVE, D("0.30"),
            research_agents=("oversold-scout", "trend-filter", "liquidity-check", "volatility-stop"), make_strategy=_contrarian),
    PodSpec("value", "Value", "Buys cheap quality", "Companies trading below estimated intrinsic value with a margin of safety.",
            "var(--shark-value)", PodStatus.INACTIVE, D("0"),
            "Needs point-in-time fundamentals (financial statements) and a valuation model; neither exists yet."),
    PodSpec("macro", "Macro", "Buys the regime", "Rates, inflation and cross-asset regime signals expressed through sector and index exposure.",
            "var(--shark-macro)", PodStatus.INACTIVE, D("0"),
            "Needs a point-in-time macro data feed and non-equity instruments; not available at $0."),
    PodSpec("earnings", "Earnings", "Buys the surprise", "Post-earnings drift and surprise events around reporting dates.",
            "var(--shark-earnings)", PodStatus.INACTIVE, D("0"),
            "Needs point-in-time earnings dates and consensus estimates; no free source qualifies."),
    PodSpec("news", "News", "Buys the headline", "Event-driven trades on filings and news flow.",
            "var(--shark-news)", PodStatus.INACTIVE, D("0"),
            "Needs a news/filings feed and LLM reading under the shared budget; not built or funded."),
)

POD_BY_ID = {p.pod_id: p for p in POD_REGISTRY}
