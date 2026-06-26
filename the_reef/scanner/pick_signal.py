"""Print the best dispatch candidate from recent signals, applying guard checks.

Guards:
  - Skip tickers with an open position in The Tank
  - Skip tickers dived in the last 4 hours (decisions collection)

Priority boost:
  - +3 effective priority for tickers nominated in the last 48h (shark intelligence layer)

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
    now = datetime.now(timezone.utc)
    cutoff_4h = (now - timedelta(hours=4)).isoformat()
    recently_dived = {
        d["ticker"] for d in db.decisions.find({"timestamp": {"$gte": cutoff_4h}})
    }
    blocked = open_tickers | recently_dived

    cutoff_48h = now - timedelta(hours=48)
    nominated = {
        d["ticker"] for d in db.nominations.find({"created_at": {"$gte": cutoff_48h}})
    }

    signals = load_signals(limit=20)
    picks = [s for s in signals if s.ticker not in blocked]
    picks.sort(key=lambda s: s.priority + (3 if s.ticker in nominated else 0), reverse=True)
    print(picks[0].ticker if picks else "")


if __name__ == "__main__":
    main()
