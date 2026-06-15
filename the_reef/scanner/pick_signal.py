"""Print the best dispatch candidate from recent signals, applying guard checks.

Guards:
  - Skip tickers with an open position in The Tank
  - Skip tickers dived in the last 4 hours (decisions collection)

Prints the ticker to stdout (empty string if nothing qualifies).
Used by deep_dive.yml fallback when no ticker is provided.
"""
from datetime import datetime, timezone, timedelta

from .monitor import load_signals
from ..brokerage.the_tank import TheTank, get_db


def main():
    tank = TheTank()
    db = get_db()

    open_tickers = set(tank.positions.keys())
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
    recently_dived = {
        d["ticker"] for d in db.decisions.find({"timestamp": {"$gte": cutoff}})
    }
    blocked = open_tickers | recently_dived

    signals = load_signals(limit=20)
    picks = [s for s in signals if s.ticker not in blocked]
    print(picks[0].ticker if picks else "")


if __name__ == "__main__":
    main()
