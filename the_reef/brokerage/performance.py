"""Performance analytics for The Tank — P&L, win rate, agent attribution."""
from typing import TYPE_CHECKING
from collections import defaultdict

if TYPE_CHECKING:
    from .the_tank import TheTank


def calculate_metrics(tank: "TheTank") -> dict:
    closed = [t for t in tank.trade_history if t.action == "SELL" and t.pnl is not None]
    wins = [t for t in closed if (t.pnl or 0.0) > 0]
    losses = [t for t in closed if (t.pnl or 0.0) <= 0]

    total_pnl = sum(t.pnl or 0.0 for t in closed) if closed else 0.0
    win_rate = len(wins) / len(closed) * 100 if closed else 0.0
    avg_win = sum(t.pnl or 0.0 for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(t.pnl or 0.0 for t in losses) / len(losses) if losses else 0.0
    loss_total = sum(t.pnl or 0.0 for t in losses)
    profit_factor = abs(sum(t.pnl or 0.0 for t in wins) / loss_total) if losses and loss_total != 0 else float("inf")

    return {
        "total_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(win_rate, 1),
        "total_realized_pnl": round(total_pnl, 2),
        "unrealized_pnl": round(sum(p.unrealized_pnl for p in tank.positions.values()), 2),
        "total_pnl": round(tank.total_pnl(), 2),
        "total_pnl_pct": round(tank.total_pnl_pct(), 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "portfolio_value": round(tank.portfolio_value(), 2),
        "cash": round(tank.cash, 2),
    }


def agent_attribution(tank: "TheTank") -> dict:
    """Score each agent by the P&L of trades they were involved in."""
    shark_scores: dict[str, list[float]] = defaultdict(list)

    for trade in tank.trade_history:
        if trade.action == "SELL" and trade.pnl is not None:
            shark_scores[trade.surfaced_by].append(trade.pnl)
            for analyst in trade.vetted_by.split(","):
                shark_scores[analyst.strip()].append(trade.pnl)

    result = {}
    for shark, pnls in shark_scores.items():
        result[shark] = {
            "trades": len(pnls),
            "total_pnl": round(sum(pnls), 2),
            "avg_pnl": round(sum(pnls) / len(pnls), 2),
            "win_rate": round(sum(1 for p in pnls if p > 0) / len(pnls) * 100, 1),
        }
    return dict(sorted(result.items(), key=lambda x: x[1]["total_pnl"], reverse=True))


def format_report(tank: "TheTank") -> str:
    metrics = calculate_metrics(tank)
    attribution = agent_attribution(tank)

    lines = [
        "=" * 56,
        "  THE REEF — PERFORMANCE REPORT",
        "=" * 56,
        f"  Portfolio Value : ${metrics['portfolio_value']:>8.2f}",
        f"  Total P&L       : ${metrics['total_pnl']:>+8.2f}  ({metrics['total_pnl_pct']:+.1f}%)",
        f"  Unrealized P&L  : ${metrics['unrealized_pnl']:>+8.2f}",
        f"  Cash Available  : ${metrics['cash']:>8.2f}",
        "-" * 56,
        f"  Closed Trades   : {metrics['total_trades']}  "
        f"(W:{metrics['wins']}  L:{metrics['losses']}  "
        f"Win%:{metrics['win_rate_pct']:.0f}%)",
        f"  Avg Win / Loss  : ${metrics['avg_win']:>+.2f} / ${metrics['avg_loss']:>+.2f}",
        f"  Profit Factor   : {metrics['profit_factor']:.2f}",
        "-" * 56,
        "  AGENT ATTRIBUTION",
    ]
    if attribution:
        for shark, stats in attribution.items():
            lines.append(
                f"  {shark:<22} P&L ${stats['total_pnl']:>+7.2f}  "
                f"Win%:{stats['win_rate']:.0f}%  ({stats['trades']} trades)"
            )
    else:
        lines.append("  No closed trades yet.")
    lines.append("=" * 56)
    return "\n".join(lines)
