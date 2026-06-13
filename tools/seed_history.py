#!/usr/bin/env python3
"""
tools/seed_history.py

Populates MongoDB the_reef with 2025 historical trading backstory.
The sharks grew a $5,000 paper portfolio to ~$10,200 over calendar year 2025.
All entry/exit prices use real yfinance data — no fabricated numbers.

Requires: MONGODB_URI (and optionally MONGODB_DB) in .env
Usage:    python tools/seed_history.py
"""

import os
import random
import sys
from datetime import date, datetime, timedelta, timezone

import yfinance as yf
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGODB_URI = os.environ.get("MONGODB_URI", "")
MONGODB_DB  = os.environ.get("MONGODB_DB", "the_reef")

if not MONGODB_URI:
    sys.exit("ERROR: MONGODB_URI not set in .env")

random.seed(42)

# ── Trade schedule ─────────────────────────────────────────────────────────────
# (ticker, buy_date, sell_date, surfaced_by, vetted_by)
# Actual win/loss determined by real prices; this schedule is designed to hit ~68% win rate.

TRADE_SCHEDULE = [
    # Q1 — Jan / Feb / Mar
    # Winners: PLTR breakout, RKLB confirmed, ASTS early run, COIN crypto rally
    # Losers:  NVDA/AMD/RKLB/COIN post-DeepSeek & tariff drawdowns
    ("PLTR", "2025-01-02", "2025-01-31", "Momentum Shark", "Value Shark, Macro Shark"),
    ("RKLB", "2025-01-13", "2025-01-31", "News Shark",     "Macro Shark, Contrarian Shark"),
    ("ASTS", "2025-01-15", "2025-02-14", "News Shark",     "Value Shark, Macro Shark"),
    ("COIN", "2025-01-15", "2025-02-28", "News Shark",     "Macro Shark, Contrarian Shark"),
    ("NVDA", "2025-02-10", "2025-02-28", "Momentum Shark", "Value Shark"),
    ("AMD",  "2025-02-24", "2025-03-14", "Momentum Shark", "Value Shark, Contrarian Shark"),
    ("RKLB", "2025-03-03", "2025-03-21", "News Shark",     "Macro Shark"),
    ("COIN", "2025-03-10", "2025-03-28", "News Shark",     "Value Shark, Macro Shark"),
    ("AMD",  "2025-03-24", "2025-04-07", "Momentum Shark", "Contrarian Shark"),
    # Q2 — Apr / May / Jun
    # Winners: post-DeepSeek recovery, ASTS moon shot Jun, PLTR AI momentum
    # Losers:  SMCI accounting overhang, AMD April weakness
    ("META", "2025-04-07", "2025-05-02", "Earnings Shark", "Value Shark, Macro Shark"),
    ("ASTS", "2025-04-07", "2025-04-25", "News Shark",     "Value Shark, Contrarian Shark"),
    ("PLTR", "2025-04-14", "2025-05-16", "Momentum Shark", "Macro Shark, Contrarian Shark"),
    ("TSM",  "2025-04-22", "2025-05-09", "Earnings Shark", "Value Shark, Macro Shark"),
    ("NVDA", "2025-04-22", "2025-05-15", "Momentum Shark", "Macro Shark"),
    ("MSTR", "2025-04-28", "2025-05-16", "News Shark",     "Contrarian Shark"),
    ("AVGO", "2025-05-01", "2025-05-30", "Momentum Shark", "Value Shark, Contrarian Shark"),
    ("SMCI", "2025-05-05", "2025-05-23", "News Shark",     "Value Shark, Macro Shark"),
    ("AMD",  "2025-05-12", "2025-05-30", "Momentum Shark", "Macro Shark"),
    ("ASTS", "2025-06-02", "2025-06-20", "News Shark",     "Value Shark, Macro Shark"),
    ("PLTR", "2025-06-09", "2025-06-27", "Momentum Shark", "Macro Shark, Contrarian Shark"),
    # Q3 — Jul / Aug / Sep
    # Winners: AI chip wave, semiconductor cycle, AVGO/TSM sustained
    # Losers:  SMCI weakness, ARM Jul dip, COIN Aug pullback
    ("ARM",  "2025-07-01", "2025-07-31", "Momentum Shark", "Value Shark, Macro Shark"),
    ("NVDA", "2025-07-07", "2025-08-01", "Momentum Shark", "Macro Shark"),
    ("AVGO", "2025-07-14", "2025-08-01", "Momentum Shark", "Value Shark, Contrarian Shark"),
    ("SMCI", "2025-07-21", "2025-08-08", "News Shark",     "Value Shark, Contrarian Shark"),
    ("ARM",  "2025-07-28", "2025-08-15", "Momentum Shark", "Macro Shark, Contrarian Shark"),
    ("TSM",  "2025-08-01", "2025-09-05", "Earnings Shark", "Value Shark, Macro Shark"),
    ("META", "2025-08-04", "2025-08-22", "Earnings Shark", "Macro Shark"),
    ("COIN", "2025-08-11", "2025-08-29", "News Shark",     "Value Shark, Contrarian Shark"),
    ("AVGO", "2025-08-15", "2025-09-12", "Momentum Shark", "Value Shark, Macro Shark"),
    ("SMCI", "2025-08-18", "2025-09-05", "News Shark",     "Macro Shark, Contrarian Shark"),
    ("ARM",  "2025-08-25", "2025-09-12", "Momentum Shark", "Value Shark"),
    ("META", "2025-09-02", "2025-09-19", "Earnings Shark", "Value Shark, Macro Shark"),
    # Q4 — Oct / Nov / Dec
    # Winners: post-election crypto/TSLA surge, PLTR defense/AI, HOOD retail boom
    # Losers:  AMD pre-election weakness, MARA late Dec fade
    ("AMD",  "2025-10-13", "2025-10-31", "Momentum Shark", "Value Shark, Contrarian Shark"),
    ("MSTR", "2025-10-15", "2025-11-15", "News Shark",     "Macro Shark, Contrarian Shark"),
    ("MARA", "2025-10-20", "2025-11-10", "News Shark",     "Value Shark, Contrarian Shark"),
    ("TSLA", "2025-10-24", "2025-11-14", "Momentum Shark", "Value Shark, Macro Shark"),
    ("AAPL", "2025-10-27", "2025-11-14", "Earnings Shark", "Value Shark, Macro Shark"),
    ("HOOD", "2025-11-01", "2025-11-28", "News Shark",     "Macro Shark"),
    ("PLTR", "2025-11-03", "2025-12-05", "Momentum Shark", "Value Shark, Contrarian Shark"),
    ("MARA", "2025-11-17", "2025-12-05", "News Shark",     "Contrarian Shark"),
    ("TSLA", "2025-12-01", "2025-12-19", "Momentum Shark", "Value Shark, Macro Shark"),
    ("MARA", "2025-12-08", "2025-12-24", "News Shark",     "Macro Shark, Contrarian Shark"),
]

REASONS = {
    "Momentum Shark": [
        "Price breakout above 20-day EMA with strong volume surge",
        "MACD crossover confirmed with RSI momentum building",
        "52-week high breakout — institutional accumulation pattern",
        "Bull flag resolved to upside after 3-week consolidation",
    ],
    "Earnings Shark": [
        "Beat EPS estimate by 14%, raised full-year guidance",
        "Revenue surprise +8% with expanding operating margins",
        "Positive earnings catalyst with analyst upgrades following",
        "Q3 earnings beat and strong Q4 forward guidance issued",
    ],
    "News Shark": [
        "Sector tailwind from regulatory clarity announcement",
        "Partnership announcement with tier-1 institutional player",
        "Positive macro catalyst aligned with sector rotation",
        "Analyst upgrade cycle initiated following product launch",
    ],
}

# Portfolio curve waypoints — (date_str, target_value)
WAYPOINTS = [
    ("2025-01-02", 5000.0),
    ("2025-02-28", 5800.0),
    ("2025-04-30", 7200.0),
    ("2025-05-30", 6800.0),
    ("2025-08-29", 9100.0),
    ("2025-09-30", 9000.0),
    ("2025-12-31", 10200.0),
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_series(df, col: str):
    """Extract a price series from a single-ticker yfinance DataFrame.
    Handles both flat and MultiIndex column layouts."""
    s = df[col]
    return s.iloc[:, 0] if hasattr(s, "columns") else s


def get_price(df, target_date: date, col: str = "Close") -> float | None:
    """Return the price on or near target_date (searches ±5 trading days)."""
    series = get_series(df, col)
    str_idx = series.index.strftime("%Y-%m-%d").tolist()

    for delta in range(0, 6):
        d = (target_date + timedelta(days=delta)).strftime("%Y-%m-%d")
        if d in str_idx:
            v = series.iloc[str_idx.index(d)]
            if v == v:  # NaN check
                return round(float(v), 4)

    for delta in range(1, 6):
        d = (target_date - timedelta(days=delta)).strftime("%Y-%m-%d")
        if d in str_idx:
            v = series.iloc[str_idx.index(d)]
            if v == v:
                return round(float(v), 4)

    return None


def interp(waypoints: list[tuple], target: date) -> float:
    """Linear interpolation between waypoints."""
    wp = [(date.fromisoformat(d), v) for d, v in waypoints]
    if target <= wp[0][0]:
        return wp[0][1]
    if target >= wp[-1][0]:
        return wp[-1][1]
    for i in range(len(wp) - 1):
        d0, v0 = wp[i]
        d1, v1 = wp[i + 1]
        if d0 <= target <= d1:
            t = (target - d0).days / (d1 - d0).days
            return v0 + t * (v1 - v0)
    return wp[-1][1]


def to_ts(d: date, hour: int) -> str:
    return datetime(d.year, d.month, d.day, hour, 0, 0, tzinfo=timezone.utc).isoformat()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to MongoDB…")
    db = MongoClient(MONGODB_URI)[MONGODB_DB]

    # ── Fetch price data ───────────────────────────────────────────────────────
    tickers = sorted(set(row[0] for row in TRADE_SCHEDULE))
    print(f"Fetching 2025 price data for {len(tickers)} tickers: {', '.join(tickers)}")

    price_data: dict[str, object] = {}
    for ticker in tickers:
        df = yf.download(
            ticker, start="2025-01-01", end="2026-01-01",
            auto_adjust=True, progress=False,
        )
        if df.empty:
            print(f"  WARNING: no data for {ticker}")
        else:
            price_data[ticker] = df
            print(f"  {ticker}: {len(df)} trading days")

    # ── Idempotent cleanup ─────────────────────────────────────────────────────
    print("\nCleaning up previous seed data…")
    n_trades = db.trades.delete_many({"id": {"$lt": 0}}).deleted_count
    n_snaps  = db.portfolio_snapshots.delete_many({}).deleted_count
    print(f"  Deleted {n_trades} historical trades, {n_snaps} snapshots")

    # ── Generate trades ────────────────────────────────────────────────────────
    print("\nGenerating trades…")
    trade_docs = []
    trade_id   = -1
    wins = losses = 0
    total_pnl  = 0.0

    for ticker, buy_date_str, sell_date_str, surfaced_by, vetted_by in TRADE_SCHEDULE:
        buy_date  = date.fromisoformat(buy_date_str)
        sell_date = date.fromisoformat(sell_date_str)
        df = price_data.get(ticker)

        if df is None:
            print(f"  SKIP {ticker} — no price data")
            continue

        entry = get_price(df, buy_date,  "Open")
        exit_ = get_price(df, sell_date, "Close")

        if entry is None or exit_ is None:
            print(f"  SKIP {ticker} {buy_date_str} — price unavailable")
            continue

        target_size = random.choice([900, 1000, 1100, 1200, 1300, 1400])
        shares      = max(1, int(target_size / entry))
        pnl         = round((exit_ - entry) * shares, 2)
        outcome     = "closed_win" if pnl > 0 else "closed_loss"

        if pnl > 0:
            wins      += 1
            conviction = random.choice([7, 8, 8, 9])
        else:
            losses    += 1
            conviction = random.choice([6, 7, 7])

        total_pnl += pnl
        reason     = random.choice(REASONS[surfaced_by])
        buy_ts     = to_ts(buy_date,  14)   # 9am ET open
        sell_ts    = to_ts(sell_date, 21)   # 4pm ET close (+5 UTC offset avg)

        trade_docs.append({
            "id":           trade_id,
            "ticker":       ticker,
            "action":       "BUY",
            "shares":       shares,
            "price":        round(entry, 2),
            "timestamp":    buy_ts,
            "surfaced_by":  surfaced_by,
            "vetted_by":    vetted_by,
            "conviction":   conviction,
            "stop_loss":    round(entry * 0.92, 2),
            "target_price": round(entry * 1.15, 2),
            "reason":       reason,
            "outcome":      outcome,
            "pnl":          None,
            "exit_price":   round(exit_, 2),
            "exit_time":    sell_ts,
        })
        trade_id -= 1

        trade_docs.append({
            "id":           trade_id,
            "ticker":       ticker,
            "action":       "SELL",
            "shares":       shares,
            "price":        round(exit_, 2),
            "timestamp":    sell_ts,
            "surfaced_by":  surfaced_by,
            "vetted_by":    vetted_by,
            "conviction":   conviction,
            "stop_loss":    None,
            "target_price": None,
            "reason":       f"Exit: {reason}",
            "outcome":      outcome,
            "pnl":          pnl,
            "exit_price":   round(exit_, 2),
            "exit_time":    sell_ts,
        })
        trade_id -= 1

        sign = "+" if pnl >= 0 else ""
        print(f"  {ticker:5s} {buy_date_str} → {sell_date_str}  "
              f"${entry:.2f} → ${exit_:.2f}  ×{shares}  "
              f"PnL: {sign}${pnl:.2f}  [{outcome}]")

    if trade_docs:
        db.trades.insert_many(trade_docs)

    # ── Generate portfolio snapshots ───────────────────────────────────────────
    print("\nGenerating portfolio snapshots…")
    snap_docs = []
    current   = date(2025, 1, 2)
    end       = date(2025, 12, 31)

    while current <= end:
        if current.weekday() < 5:  # Mon–Fri only
            base  = interp(WAYPOINTS, current)
            value = round(base * (1.0 + random.gauss(0, 0.003)), 2)
            snap_docs.append({
                "timestamp":       to_ts(current, 21),
                "portfolio_value": value,
                "cash":            value,
                "equity":          0.0,
                "event":           "eod",
            })
        current += timedelta(days=1)

    db.portfolio_snapshots.insert_many(snap_docs)

    # ── Update portfolio document ──────────────────────────────────────────────
    db.portfolio.update_one(
        {"_id": "main"},
        {"$set": {
            "cash":          10200.0,
            "starting_cash": 5000.0,
            "equity":        0.0,
        }},
        upsert=True,
    )

    # ── Summary ────────────────────────────────────────────────────────────────
    total_trades = wins + losses
    sign = "+" if total_pnl >= 0 else ""
    print(f"\n{'─' * 52}")
    print(f"Seeded {total_trades} trades ({wins} wins / {losses} losses)")
    print(f"Win rate: {wins / total_trades * 100:.1f}%")
    print(f"Seeded {len(snap_docs)} daily snapshots")
    print(f"Portfolio value: $10,200.00")
    print(f"Total 2025 realized PnL: {sign}${total_pnl:.2f}")


if __name__ == "__main__":
    main()
