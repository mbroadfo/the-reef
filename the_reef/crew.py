"""The Reef — CrewAI orchestration layer.

Sequential process: Hunter → Value → Macro → Contrarian → Apex Shark.
Apex Shark has The Tank tools to check portfolio state and execute paper trades.
"""
from __future__ import annotations

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import SerperDevTool

from .tools.market_data import GetPriceTool, GetHistoryTool
from .tools.tank_tools import (
    GetPortfolioTool, ExecuteBuyTool, ExecuteSellTool, CheckStopLossesTool,
    set_tank,
)
from .brokerage.the_tank import TheTank
from .scanner.monitor import ScanSignal


_market_tools = [GetPriceTool(), GetHistoryTool(), SerperDevTool()]
_apex_tools = [GetPortfolioTool(), ExecuteBuyTool(), ExecuteSellTool(), CheckStopLossesTool()]


@CrewBase
class TheReefCrew:
    """The Reef — three-tier shark hierarchy."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self, tank: TheTank | None = None):
        super().__init__()
        self._tank = tank or TheTank()
        set_tank(self._tank)

    # ── Tier 1: Hunter Sharks ─────────────────────────────────────────────────

    @agent
    def momentum_shark(self) -> Agent:
        return Agent(
            config=self.agents_config["momentum_shark"],
            tools=_market_tools,
            verbose=True,
        )

    @agent
    def earnings_shark(self) -> Agent:
        return Agent(
            config=self.agents_config["earnings_shark"],
            tools=_market_tools,
            verbose=True,
        )

    @agent
    def news_shark(self) -> Agent:
        return Agent(
            config=self.agents_config["news_shark"],
            tools=_market_tools,
            verbose=True,
        )

    # ── Tier 2: Analyst Sharks ────────────────────────────────────────────────

    @agent
    def value_shark(self) -> Agent:
        return Agent(
            config=self.agents_config["value_shark"],
            tools=_market_tools,
            verbose=True,
        )

    @agent
    def macro_shark(self) -> Agent:
        return Agent(
            config=self.agents_config["macro_shark"],
            tools=[SerperDevTool()],
            verbose=True,
        )

    @agent
    def contrarian_shark(self) -> Agent:
        return Agent(
            config=self.agents_config["contrarian_shark"],
            tools=[SerperDevTool()],
            verbose=True,
        )

    # ── Tier 3: Apex Shark ────────────────────────────────────────────────────

    @agent
    def apex_shark(self) -> Agent:
        return Agent(
            config=self.agents_config["apex_shark"],
            tools=_apex_tools,
            verbose=True,
        )

    # ── Tasks ─────────────────────────────────────────────────────────────────

    @task
    def hunter_research(self) -> Task:
        return Task(config=self.tasks_config["hunter_research"])

    @task
    def value_analysis(self) -> Task:
        return Task(config=self.tasks_config["value_analysis"])

    @task
    def macro_analysis(self) -> Task:
        return Task(config=self.tasks_config["macro_analysis"])

    @task
    def contrarian_challenge(self) -> Task:
        return Task(config=self.tasks_config["contrarian_challenge"])

    @task
    def apex_decision(self) -> Task:
        return Task(
            config=self.tasks_config["apex_decision"],
            output_file="data/last_decision.md",
        )

    # ── Crew ──────────────────────────────────────────────────────────────────

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )

    def select_hunter(self, signal_type: str) -> Agent:
        """Map signal type to the most relevant hunter shark."""
        mapping = {
            "VOLUME_SPIKE": self.momentum_shark(),
            "PRICE_BREAKOUT": self.momentum_shark(),
            "PRICE_DROP": self.momentum_shark(),
            "RSI_OVERSOLD": self.momentum_shark(),
            "RSI_OVERBOUGHT": self.contrarian_shark(),
            "EARNINGS_UPCOMING": self.earnings_shark(),
            "NEWS_SENTIMENT": self.news_shark(),
        }
        return mapping.get(signal_type, self.momentum_shark())


def run_deep_dive(signal: ScanSignal, tank: TheTank | None = None) -> str:
    """Run the full shark panel on a scanner signal. Returns Apex Shark's decision."""
    reef = TheReefCrew(tank=tank)

    # Override the hunter task's agent based on signal type
    hunter_task = reef.hunter_research()
    hunter_task.agent = reef.select_hunter(signal.signal_type)

    inputs = {
        "ticker": signal.ticker,
        "signal_type": signal.signal_type,
        "signal_value": signal.value,
        "current_price": signal.price,
        "scan_timestamp": signal.timestamp,
    }

    result = reef.crew().kickoff(inputs=inputs)
    return result.raw


def run_stop_loss_check(tank: TheTank | None = None) -> str:
    """Autonomous stop-loss check — Apex Shark reviews all positions."""
    from .tools.tank_tools import set_tank, CheckStopLossesTool, ExecuteSellTool
    from .tools.market_data import get_price

    active_tank = tank or TheTank()
    set_tank(active_tank)

    positions = active_tank.positions
    if not positions:
        return "No open positions to review."

    # Refresh prices
    prices = {ticker: get_price(ticker) for ticker in positions}
    active_tank.update_prices({t: p for t, p in prices.items() if p is not None})

    triggered = active_tank.check_stop_losses()
    results = []
    for ticker, price in triggered:
        _, msg = active_tank.sell(
            ticker=ticker,
            shares=active_tank.positions[ticker].shares,
            price=price,
            reason="Stop-loss triggered — autonomous Apex Shark exit",
            outcome="stopped_out",
        )
        results.append(f"STOPPED OUT: {msg}")

    return "\n".join(results) if results else "All positions within stop-loss bounds."
