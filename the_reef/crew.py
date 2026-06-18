"""The Reef — CrewAI orchestration layer.

Sequential pipeline: Hunter → Research → Macro → Sentiment →
Contrarian → Risk → Wildcard → Apex Shark.
Apex Shark has The Tank tools to check portfolio state and execute paper trades.
"""
from __future__ import annotations

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import SerperDevTool

from .tools.market_data import GetPriceTool, GetHistoryTool
from .tools.tank_tools import (
    GetPortfolioTool, ExecuteBuyTool, ExecuteSellTool, CheckStopLossesTool,
    NominateTickerTool, set_tank,
)
from .tools.shark_history_tool import GetSharkHistoryTool
from .brokerage.the_tank import TheTank
from .scanner.monitor import ScanSignal


_market_tools = [GetPriceTool(), GetHistoryTool(), SerperDevTool()]
_nominate_tool = [NominateTickerTool()]
_apex_tools = [
    GetPortfolioTool(), ExecuteBuyTool(), ExecuteSellTool(),
    CheckStopLossesTool(), GetSharkHistoryTool(), NominateTickerTool(),
]


@CrewBase
class TheReefCrew:
    """The Reef — 8-shark investment committee."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    # ── Hunters ───────────────────────────────────────────────────────────────

    @agent
    def hunter_shark(self) -> Agent:
        return Agent(
            config=self.agents_config["hunter_shark"],
            tools=_market_tools,
            verbose=True,
        )

    @agent
    def research_shark(self) -> Agent:
        return Agent(
            config=self.agents_config["research_shark"],
            tools=_market_tools,
            verbose=True,
        )

    @agent
    def wildcard_shark(self) -> Agent:
        return Agent(
            config=self.agents_config["wildcard_shark"],
            tools=_market_tools + [SerperDevTool()] + _nominate_tool,
            verbose=True,
        )

    # ── Analysts ──────────────────────────────────────────────────────────────

    @agent
    def macro_shark(self) -> Agent:
        return Agent(
            config=self.agents_config["macro_shark"],
            tools=[SerperDevTool()] + _nominate_tool,
            verbose=True,
        )

    @agent
    def sentiment_shark(self) -> Agent:
        return Agent(
            config=self.agents_config["sentiment_shark"],
            tools=[SerperDevTool()] + _nominate_tool,
            verbose=True,
        )

    @agent
    def contrarian_shark(self) -> Agent:
        return Agent(
            config=self.agents_config["contrarian_shark"],
            tools=[SerperDevTool()],
            verbose=True,
        )

    @agent
    def risk_shark(self) -> Agent:
        return Agent(
            config=self.agents_config["risk_shark"],
            tools=[GetPortfolioTool()],
            verbose=True,
        )

    # ── Apex ──────────────────────────────────────────────────────────────────

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
    def research_analysis(self) -> Task:
        return Task(config=self.tasks_config["research_analysis"])

    @task
    def macro_analysis(self) -> Task:
        return Task(config=self.tasks_config["macro_analysis"])

    @task
    def sentiment_analysis(self) -> Task:
        return Task(config=self.tasks_config["sentiment_analysis"])

    @task
    def contrarian_challenge(self) -> Task:
        return Task(config=self.tasks_config["contrarian_challenge"])

    @task
    def risk_assessment(self) -> Task:
        return Task(config=self.tasks_config["risk_assessment"])

    @task
    def wildcard_nomination(self) -> Task:
        return Task(config=self.tasks_config["wildcard_nomination"])

    @task
    def apex_decision(self) -> Task:
        return Task(config=self.tasks_config["apex_decision"])

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
        """Map signal type to the most relevant shark for hunter_research."""
        mapping = {
            "VOLUME_SPIKE":       self.hunter_shark(),
            "PRICE_BREAKOUT":     self.hunter_shark(),
            "PRICE_DROP":         self.contrarian_shark(),
            "RSI_OVERSOLD":       self.contrarian_shark(),
            "RSI_OVERBOUGHT":     self.contrarian_shark(),
            "EARNINGS_UPCOMING":  self.research_shark(),
            "NEWS_SENTIMENT":     self.sentiment_shark(),
            "IPO_LISTING":        self.research_shark(),  # No tape to read — go straight to fundamentals
        }
        return mapping.get(signal_type, self.hunter_shark())


def run_deep_dive(signal: ScanSignal, tank: TheTank | None = None) -> str:
    """Run the full shark panel on a scanner signal. Returns Apex Shark's decision."""
    set_tank(tank or TheTank())
    reef = TheReefCrew()

    # Override the hunter task's agent based on signal type
    hunter_task = reef.hunter_research()
    hunter_task.agent = reef.select_hunter(signal.signal_type)

    ipo_note = ""
    if signal.signal_type == "IPO_LISTING":
        ipo_note = (
            "IMPORTANT — IPO CONTEXT: This stock has minimal price history (days, not months). "
            "Do NOT attempt RSI, 20-day volume averages, or multi-week technical patterns — "
            "that data does not exist yet. Instead focus on: S-1/prospectus revenue and margins, "
            "Morningstar or analyst fair value estimates, post-IPO float and lock-up period "
            "end date, valuation vs comparable public companies, and first-week trading "
            "range dynamics. Treat this as a fundamental + sentiment analysis, not a technical one."
        )

    inputs = {
        "ticker": signal.ticker,
        "signal_type": signal.signal_type,
        "signal_value": signal.value,
        "current_price": signal.price,
        "scan_timestamp": signal.timestamp,
        "ipo_note": ipo_note,
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
        pos = active_tank.positions[ticker]
        ok, msg = active_tank.sell(
            ticker=ticker,
            shares=pos.shares,
            price=price,
            reason="Stop-loss triggered — autonomous Apex Shark exit",
            outcome="stopped_out",
        )
        results.append(f"STOPPED OUT: {msg}")
        if ok:
            from .notifications.sms import send_sms
            pnl = (price - pos.entry_price) * pos.shares
            pnl_str = f"+${pnl:.0f}" if pnl >= 0 else f"-${abs(pnl):.0f}"
            send_sms(
                "REEF STOP",
                f"STOPPED OUT {int(pos.shares)} {ticker} @ ${price:.2f}\n"
                f"Entry ${pos.entry_price:.2f} | P&L {pnl_str}\n"
                f"Cash: ${active_tank.cash:,.0f}",
            )

    return "\n".join(results) if results else "All positions within stop-loss bounds."
