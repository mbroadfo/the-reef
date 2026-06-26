#!/usr/bin/env python3
"""Daily conviction points reset — run at market open (09:30 ET).

Upserts a fresh shark_points doc for each of the 7 bidding sharks:
points_total=10, points_spent=0, points_remaining=10, bids=[].

Triggered by GitHub Actions at 13:30 UTC Mon-Fri.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from the_reef.brokerage.the_tank import get_db  # noqa: E402

SHARKS = [
    "hunter_shark", "research_shark", "macro_shark", "sentiment_shark",
    "contrarian_shark", "risk_shark", "wildcard_shark",
]
POINTS_PER_DAY = 10


def reset_conviction_points():
    db = get_db()
    today = date.today().isoformat()

    for shark_id in SHARKS:
        db.shark_points.update_one(
            {"date": today, "shark_id": shark_id},
            {"$set": {
                "date": today,
                "shark_id": shark_id,
                "points_total": POINTS_PER_DAY,
                "points_spent": 0,
                "points_remaining": POINTS_PER_DAY,
                "bids": [],
            }},
            upsert=True,
        )
        print(f"Reset: {shark_id} — {POINTS_PER_DAY} pts for {today}")

    print(f"Done — {len(SHARKS)} sharks reset for {today}")


if __name__ == "__main__":
    reset_conviction_points()
