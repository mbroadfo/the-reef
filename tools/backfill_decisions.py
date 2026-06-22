"""Backfill decisions collection from BUY trades that have no decision logged.

Idempotent: skips any ticker+timestamp combo already in decisions.
"""
from __future__ import annotations
import os
from datetime import datetime, timezone
from pymongo import MongoClient


def main():
    db_name = os.environ.get("DB_NAME", "the_reef")
    password = os.environ["MONGODB_PASSWORD"]
    uri = f"mongodb+srv://reef-admin:{password}@reef-m0.mongodb.net/{db_name}?retryWrites=true&w=majority"
    db = MongoClient(uri)[db_name]

    # Build a set of (ticker, timestamp) already in decisions for dedup
    existing = {
        (d["ticker"], d.get("timestamp"))
        for d in db.decisions.find({}, {"ticker": 1, "timestamp": 1})
    }

    buys = list(db.trades.find({"action": "BUY"}).sort("id", 1))
    inserted = 0
    skipped = 0

    for trade in buys:
        ticker = trade["ticker"]
        ts = trade.get("timestamp")
        key = (ticker, ts)
        if key in existing:
            skipped += 1
            continue

        surfaced = trade.get("surfaced_by", "hunter_shark")
        vetted   = trade.get("vetted_by", "")
        reason   = trade.get("reason", "")
        conviction = trade.get("conviction", 5)

        rationale = f"Surfaced by {surfaced}."
        if vetted:
            rationale += f" Vetted by {vetted}."
        if reason:
            rationale += f" {reason}"

        db.decisions.insert_one({
            "ticker": ticker,
            "signal_type": "TRADE_EXECUTION",
            "decision": "BUY",
            "conviction": conviction,
            "rationale": rationale[:2000],
            "timestamp": ts or datetime.now(timezone.utc),
        })
        print(f"  [inserted] {ticker}  conviction={conviction}  ts={ts}")
        inserted += 1

    print(f"\n  Backfill complete: {inserted} inserted, {skipped} skipped (already existed)")
    if inserted == 0 and skipped == 0:
        print("  No BUY trades found.")


if __name__ == "__main__":
    main()
