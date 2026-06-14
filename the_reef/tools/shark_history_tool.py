from crewai.tools import BaseTool
import os

from pymongo import MongoClient


class GetSharkHistoryTool(BaseTool):
    name: str = "Get Shark Performance History"
    description: str = (
        "Returns historical win rates and P&L for each shark hunter. "
        "Use this BEFORE making any trade decision to know which sharks "
        "have been accurate and how much weight to give their recommendations."
    )

    def _run(self) -> str:
        uri = os.environ.get("MONGODB_URI", "")
        db_name = os.environ.get("MONGODB_DB", "the_reef")
        db = MongoClient(uri)[db_name]

        trades = list(db.trades.find(
            {"action": "SELL", "pnl": {"$ne": None}}
        ))

        if not trades:
            return "No historical trade data available yet."

        stats: dict[str, dict] = {}
        for t in trades:
            hunter = t.get("surfaced_by", "Unknown")
            pnl = t.get("pnl") or 0.0
            sig = t.get("signal_type", "UNKNOWN")

            if hunter not in stats:
                stats[hunter] = {"wins": 0, "losses": 0, "total_pnl": 0.0, "by_signal": {}}

            s = stats[hunter]
            s["total_pnl"] += pnl
            if pnl > 0:
                s["wins"] += 1
            else:
                s["losses"] += 1

            if sig not in s["by_signal"]:
                s["by_signal"][sig] = {"wins": 0, "losses": 0}
            if pnl > 0:
                s["by_signal"][sig]["wins"] += 1
            else:
                s["by_signal"][sig]["losses"] += 1

        lines = ["=== SHARK PERFORMANCE HISTORY ===\n"]
        for hunter, s in sorted(
            stats.items(),
            key=lambda x: x[1]["wins"] / max(x[1]["wins"] + x[1]["losses"], 1),
            reverse=True,
        ):
            w = s["wins"]
            l = s["losses"]
            t = w + l
            wr = w / t * 100 if t else 0
            pnl = s["total_pnl"]
            sign = "+" if pnl >= 0 else ""
            lines.append(f"{hunter}: {w}W/{l}L ({wr:.0f}% win rate) PnL: {sign}${pnl:.2f}")

            for sig, sv in s["by_signal"].items():
                sw = sv["wins"]
                sl = sv["losses"]
                st = sw + sl
                swr = sw / st * 100 if st else 0
                lines.append(f"  {sig}: {sw}W/{sl}L ({swr:.0f}%)")

        lines.append("\nWEIGHTING GUIDANCE FOR APEX:")
        lines.append("83%+ win rate  -> weight heavily (STRONG signal)")
        lines.append("65-82%         -> standard weight")
        lines.append("50-64%         -> moderate weight, verify with analysts")
        lines.append("<50%           -> low weight; use as stress-tester only")

        return "\n".join(lines)
