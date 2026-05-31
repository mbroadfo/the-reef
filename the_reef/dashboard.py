"""Rich terminal dashboard — live portfolio view for The Reef."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from .brokerage.the_tank import TheTank
from .brokerage.performance import calculate_metrics, agent_attribution, format_report
from .tools.market_data import get_price
from .scanner.monitor import load_signals, SIGNALS_FILE

console = Console()


def _color_pnl(value: float) -> str:
    return "green" if value >= 0 else "red"


def build_portfolio_panel(tank: TheTank) -> Panel:
    metrics = calculate_metrics(tank)
    positions = tank.positions

    t = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    t.add_column("Ticker", style="bold white", width=8)
    t.add_column("Shares", justify="right", width=8)
    t.add_column("Entry", justify="right", width=8)
    t.add_column("Current", justify="right", width=9)
    t.add_column("P&L $", justify="right", width=9)
    t.add_column("P&L %", justify="right", width=8)
    t.add_column("Stop", justify="right", width=8)
    t.add_column("Target", justify="right", width=8)
    t.add_column("Surfaced By", width=18)

    if positions:
        for ticker, pos in positions.items():
            pnl_color = _color_pnl(pos.unrealized_pnl)
            t.add_row(
                ticker,
                f"{pos.shares:.2f}",
                f"${pos.entry_price:.2f}",
                f"${pos.current_price:.2f}",
                Text(f"${pos.unrealized_pnl:+.2f}", style=pnl_color),
                Text(f"{pos.unrealized_pnl_pct:+.1f}%", style=pnl_color),
                f"${pos.stop_loss:.2f}" if pos.stop_loss else "—",
                f"${pos.target_price:.2f}" if pos.target_price else "—",
                pos.surfaced_by,
            )
    else:
        t.add_row("—", "—", "—", "—", "—", "—", "—", "—", "No positions")

    total_pnl_color = _color_pnl(metrics["total_pnl"])
    header = (
        f"[bold]Portfolio ${metrics['portfolio_value']:.2f}[/bold]  |  "
        f"Cash [cyan]${metrics['cash']:.2f}[/cyan]  |  "
        f"Total P&L [{total_pnl_color}]{metrics['total_pnl']:+.2f} ({metrics['total_pnl_pct']:+.1f}%)[/{total_pnl_color}]"
    )
    return Panel(t, title=f"[bold yellow]THE TANK — POSITIONS[/bold yellow]  {header}", border_style="yellow")


def build_signals_panel() -> Panel:
    signals = load_signals()
    t = Table(box=box.SIMPLE, show_header=True, header_style="bold magenta")
    t.add_column("Ticker", width=7)
    t.add_column("Signal", width=18)
    t.add_column("Value", justify="right", width=8)
    t.add_column("Price", justify="right", width=8)
    t.add_column("Time", width=22)

    if signals:
        for s in signals[:8]:
            t.add_row(s.ticker, s.signal_type, f"{s.value:.2f}", f"${s.price:.2f}", s.timestamp[:19])
    else:
        t.add_row("—", "No signals yet", "—", "—", "—")

    return Panel(t, title="[bold magenta]🦈 SCANNER SIGNALS[/bold magenta]", border_style="magenta")


def build_performance_panel(tank: TheTank) -> Panel:
    metrics = calculate_metrics(tank)
    attribution = agent_attribution(tank)

    lines = []
    lines.append(f"Trades: {metrics['total_trades']}  W:{metrics['wins']}  L:{metrics['losses']}  Win%:{metrics['win_rate_pct']:.0f}%")
    lines.append(f"Avg Win: ${metrics['avg_win']:+.2f}  |  Avg Loss: ${metrics['avg_loss']:+.2f}  |  Profit Factor: {metrics['profit_factor']:.2f}")

    if attribution:
        lines.append("")
        lines.append("[bold]Agent Attribution:[/bold]")
        for shark, stats in list(attribution.items())[:5]:
            color = _color_pnl(stats["total_pnl"])
            lines.append(
                f"  {shark:<22} [{color}]{stats['total_pnl']:>+7.2f}[/{color}]  "
                f"Win%:{stats['win_rate']:.0f}%"
            )

    content = "\n".join(lines)
    return Panel(content, title="[bold green]PERFORMANCE[/bold green]", border_style="green")


def build_etrade_panel(tank: TheTank) -> Panel:
    """Shows the most recent Apex Shark decision as an eTrade action item."""
    decision_file = Path("data/last_decision.md")
    if decision_file.exists():
        content = decision_file.read_text()[:600]
    else:
        content = "Awaiting first Apex Shark decision..."

    return Panel(
        content,
        title="[bold blue]👑 APEX SHARK — LAST DECISION[/bold blue]",
        border_style="blue",
    )


def render_once(tank: TheTank):
    """Single-shot render — for GitHub Actions or non-live use."""
    console.print(build_portfolio_panel(tank))
    console.print(build_signals_panel())
    console.print(build_performance_panel(tank))
    console.print(build_etrade_panel(tank))


def run_live_dashboard(tank: TheTank, refresh_secs: int = 30):
    """Live updating dashboard — runs until Ctrl+C."""
    console.print("[bold yellow]The Reef[/bold yellow] — live dashboard starting (Ctrl+C to exit)")

    def refresh_prices():
        positions = tank.positions
        if positions:
            prices = {ticker: get_price(ticker) for ticker in positions}
            tank.update_prices({t: p for t, p in prices.items() if p is not None})

    layout = Layout()
    layout.split_column(
        Layout(name="top", size=16),
        Layout(name="bottom"),
    )
    layout["bottom"].split_row(
        Layout(name="signals"),
        Layout(name="performance"),
        Layout(name="etrade"),
    )

    with Live(layout, refresh_per_second=0.5, screen=True):
        while True:
            refresh_prices()
            layout["top"].update(build_portfolio_panel(tank))
            layout["signals"].update(build_signals_panel())
            layout["performance"].update(build_performance_panel(tank))
            layout["etrade"].update(build_etrade_panel(tank))
            time.sleep(refresh_secs)
