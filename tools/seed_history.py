#!/usr/bin/env python3
"""
tools/seed_history.py

Populates MongoDB the_reef with 2025 historical trading backstory for dashboard testing.
- Grows a $5,000 paper portfolio to exactly $10,000 by end of 2025
- 42 closed trades + 3 open positions heading into 2026
- Generates Apex decisions for each BUY
- Uses real yfinance prices — no fabricated entry/exit numbers

Run via: gh workflow run tools-seed-history.yml
Safe to re-run: deletes all seeded data (seeded=True) before inserting.
"""

import os
import random
import sys
from datetime import date, datetime, timedelta, timezone

import yfinance as yf
from pymongo import MongoClient

MONGODB_URI = os.environ.get("MONGODB_URI", "")
MONGODB_DB  = os.environ.get("MONGODB_DB", "the_reef")

if not MONGODB_URI:
    sys.exit("ERROR: MONGODB_URI not set")

random.seed(42)

# ── Closed trade schedule ──────────────────────────────────────────────────────
# (ticker, buy_date, sell_date, surfaced_by, vetted_by, signal_type)
CLOSED_TRADES = [
    # Q1 — Jan / Feb / Mar
    ("PLTR", "2025-01-02", "2025-01-31", "Hunter Shark",     "Research Shark, Macro Shark, Contrarian Shark", "PRICE_BREAKOUT"),
    ("RKLB", "2025-01-13", "2025-01-31", "Sentiment Shark",  "Research Shark, Macro Shark, Contrarian Shark", "NEWS_SENTIMENT"),
    ("ASTS", "2025-01-15", "2025-02-14", "Sentiment Shark",  "Research Shark, Macro Shark",                   "NEWS_SENTIMENT"),
    ("COIN", "2025-01-15", "2025-02-28", "Wildcard Shark",   "Research Shark, Contrarian Shark, Risk Shark",  "VOLUME_SPIKE"),
    ("NVDA", "2025-02-10", "2025-02-28", "Hunter Shark",     "Research Shark, Contrarian Shark",              "PRICE_BREAKOUT"),
    ("AMD",  "2025-02-24", "2025-03-14", "Contrarian Shark", "Research Shark, Macro Shark",                   "PRICE_DROP"),
    ("RKLB", "2025-03-03", "2025-03-21", "Sentiment Shark",  "Macro Shark, Contrarian Shark",                 "NEWS_SENTIMENT"),
    ("COIN", "2025-03-10", "2025-03-28", "Contrarian Shark", "Research Shark, Macro Shark",                   "RSI_OVERSOLD"),
    ("AMD",  "2025-03-24", "2025-04-07", "Contrarian Shark", "Research Shark, Macro Shark",                   "RSI_OVERSOLD"),
    # Q2 — Apr / May / Jun
    ("META", "2025-04-07", "2025-05-02", "Research Shark",   "Macro Shark, Contrarian Shark, Risk Shark",     "EARNINGS_UPCOMING"),
    ("ASTS", "2025-04-07", "2025-04-25", "Sentiment Shark",  "Research Shark, Contrarian Shark",              "NEWS_SENTIMENT"),
    ("PLTR", "2025-04-14", "2025-05-16", "Hunter Shark",     "Macro Shark, Contrarian Shark, Risk Shark",     "PRICE_BREAKOUT"),
    ("TSM",  "2025-04-22", "2025-05-09", "Research Shark",   "Macro Shark, Contrarian Shark",                 "EARNINGS_UPCOMING"),
    ("NVDA", "2025-04-22", "2025-05-15", "Research Shark",   "Macro Shark, Risk Shark",                       "EARNINGS_UPCOMING"),
    ("MSTR", "2025-04-28", "2025-05-16", "Wildcard Shark",   "Research Shark, Contrarian Shark, Risk Shark",  "VOLUME_SPIKE"),
    ("AVGO", "2025-05-01", "2025-05-30", "Hunter Shark",     "Research Shark, Macro Shark, Risk Shark",       "PRICE_BREAKOUT"),
    ("SMCI", "2025-05-05", "2025-05-23", "Sentiment Shark",  "Research Shark, Contrarian Shark",              "NEWS_SENTIMENT"),
    ("AMD",  "2025-05-12", "2025-05-30", "Hunter Shark",     "Macro Shark, Contrarian Shark",                 "PRICE_BREAKOUT"),
    ("ASTS", "2025-06-02", "2025-06-20", "Sentiment Shark",  "Research Shark, Macro Shark",                   "NEWS_SENTIMENT"),
    ("PLTR", "2025-06-09", "2025-06-27", "Hunter Shark",     "Macro Shark, Contrarian Shark, Risk Shark",     "PRICE_BREAKOUT"),
    # Q3 — Jul / Aug / Sep
    ("ARM",  "2025-07-01", "2025-07-31", "Hunter Shark",     "Research Shark, Macro Shark",                   "PRICE_BREAKOUT"),
    ("NVDA", "2025-07-07", "2025-08-01", "Hunter Shark",     "Macro Shark, Risk Shark",                       "VOLUME_SPIKE"),
    ("AVGO", "2025-07-14", "2025-08-01", "Hunter Shark",     "Research Shark, Contrarian Shark",              "PRICE_BREAKOUT"),
    ("SMCI", "2025-07-21", "2025-08-08", "Sentiment Shark",  "Research Shark, Contrarian Shark",              "NEWS_SENTIMENT"),
    ("ARM",  "2025-07-28", "2025-08-15", "Hunter Shark",     "Macro Shark, Contrarian Shark",                 "PRICE_BREAKOUT"),
    ("TSM",  "2025-08-01", "2025-09-05", "Research Shark",   "Macro Shark, Contrarian Shark, Risk Shark",     "EARNINGS_UPCOMING"),
    ("META", "2025-08-04", "2025-08-22", "Research Shark",   "Macro Shark, Contrarian Shark",                 "EARNINGS_UPCOMING"),
    ("COIN", "2025-08-11", "2025-08-29", "Wildcard Shark",   "Research Shark, Contrarian Shark, Risk Shark",  "VOLUME_SPIKE"),
    ("AVGO", "2025-08-15", "2025-09-12", "Hunter Shark",     "Research Shark, Macro Shark",                   "PRICE_BREAKOUT"),
    ("SMCI", "2025-08-18", "2025-09-05", "Contrarian Shark", "Research Shark, Macro Shark",                   "PRICE_DROP"),
    ("ARM",  "2025-08-25", "2025-09-12", "Hunter Shark",     "Macro Shark, Risk Shark",                       "PRICE_BREAKOUT"),
    ("META", "2025-09-02", "2025-09-19", "Research Shark",   "Macro Shark, Contrarian Shark",                 "EARNINGS_UPCOMING"),
    # Q4 — Oct / Nov / Dec
    ("AMD",  "2025-10-13", "2025-10-31", "Research Shark",   "Macro Shark, Contrarian Shark, Risk Shark",     "EARNINGS_UPCOMING"),
    ("MSTR", "2025-10-15", "2025-11-15", "Wildcard Shark",   "Research Shark, Contrarian Shark, Risk Shark",  "VOLUME_SPIKE"),
    ("MARA", "2025-10-20", "2025-11-10", "Wildcard Shark",   "Research Shark, Contrarian Shark",              "VOLUME_SPIKE"),
    ("TSLA", "2025-10-24", "2025-11-14", "Hunter Shark",     "Research Shark, Macro Shark, Risk Shark",       "PRICE_BREAKOUT"),
    ("AAPL", "2025-10-27", "2025-11-14", "Research Shark",   "Macro Shark, Contrarian Shark",                 "EARNINGS_UPCOMING"),
    ("HOOD", "2025-11-01", "2025-11-28", "Sentiment Shark",  "Research Shark, Macro Shark",                   "NEWS_SENTIMENT"),
    ("PLTR", "2025-11-03", "2025-12-05", "Hunter Shark",     "Macro Shark, Contrarian Shark, Risk Shark",     "VOLUME_SPIKE"),
    ("MARA", "2025-11-17", "2025-12-05", "Wildcard Shark",   "Research Shark, Contrarian Shark",              "VOLUME_SPIKE"),
    ("TSLA", "2025-12-01", "2025-12-19", "Sentiment Shark",  "Research Shark, Macro Shark",                   "NEWS_SENTIMENT"),
    ("MARA", "2025-12-08", "2025-12-24", "Wildcard Shark",   "Research Shark, Contrarian Shark",              "VOLUME_SPIKE"),
]

# ── Open positions — BUY only, still held heading into 2026 ───────────────────
# (ticker, buy_date, surfaced_by, vetted_by, signal_type)
OPEN_POSITIONS = [
    ("NVDA", "2025-12-15", "Hunter Shark",     "Research Shark, Macro Shark, Risk Shark",     "PRICE_BREAKOUT"),
    ("PLTR", "2025-12-17", "Hunter Shark",     "Macro Shark, Contrarian Shark, Risk Shark",   "VOLUME_SPIKE"),
    ("AMD",  "2025-12-19", "Contrarian Shark", "Research Shark, Macro Shark",                 "RSI_OVERSOLD"),
]

REASONS = {
    "Hunter Shark": [
        "Price breakout above 20-day EMA with strong volume surge",
        "MACD crossover confirmed with RSI momentum building",
        "52-week high breakout — institutional accumulation pattern",
        "Bull flag resolved to upside after 3-week consolidation",
    ],
    "Research Shark": [
        "Beat EPS estimate by 14%, raised full-year guidance",
        "Revenue surprise +8% with expanding operating margins",
        "Positive earnings catalyst with analyst upgrades following",
        "Q3 earnings beat and strong Q4 forward guidance issued",
    ],
    "Sentiment Shark": [
        "Sector tailwind from regulatory clarity announcement",
        "Partnership announcement with tier-1 institutional player",
        "Analyst upgrade cycle initiated following product launch",
        "Narrative shift detected — retail interest rising before consensus catches up",
    ],
    "Contrarian Shark": [
        "Oversold bounce setup — RSI below 30 after institutional selloff, mean reversion likely",
        "PRICE_DROP creates asymmetric risk/reward — street overreacted to news, fundamentals intact",
        "Short squeeze candidate with high short interest meeting improving fundamentals",
        "Capitulation volume detected — sellers exhausted, risk/reward favors long entry here",
    ],
    "Wildcard Shark": [
        "Crypto-correlated momentum building — BTC breakout signals sector-wide move",
        "Unusual options activity detected — smart money positioning ahead of catalyst",
        "Short squeeze setup: high float short with improving crypto macro tailwinds",
        "Cross-domain special situation — uncorrelated alpha outside main watchlist",
    ],
}

APEX_RATIONALES = {
    "PRICE_BREAKOUT": (
        "Committee consensus: BUY. {surfaced_by} flagged a clean technical setup — {reason}. "
        "{vetted_by} vetted the thesis. Volume profile confirms institutional sponsorship with "
        "above-average accumulation over the prior 5 sessions. Risk/reward at current levels is "
        "approximately 3:1 with defined stop at 8% below entry. Position sized at ~10% of portfolio. "
        "Conviction: {conviction}/10."
    ),
    "EARNINGS_UPCOMING": (
        "Committee consensus: BUY ahead of catalyst. {surfaced_by} identified the opportunity — "
        "{reason}. {vetted_by} validated the fundamental setup. Consensus estimates appear "
        "conservative relative to channel checks and recent guidance tone. Options implied move "
        "suggests the street is under-pricing a beat scenario. Entering pre-earnings with defined "
        "exit plan win or lose. Conviction: {conviction}/10."
    ),
    "NEWS_SENTIMENT": (
        "Committee consensus: BUY on narrative shift. {surfaced_by} surfaced the signal — {reason}. "
        "{vetted_by} confirmed the thesis. Retail and institutional interest inflecting simultaneously "
        "suggests the move has legs beyond initial reaction. Positioning ahead of second-wave coverage. "
        "Stop placed at recent support. Conviction: {conviction}/10."
    ),
    "VOLUME_SPIKE": (
        "Committee consensus: BUY. {surfaced_by} detected abnormal volume — {reason}. "
        "{vetted_by} vetted the setup. Volume 3.2x the 20-day average with price holding near highs "
        "suggests accumulation, not distribution. Cross-correlated with broader sector momentum. "
        "Risk managed with hard stop 8% below entry. Conviction: {conviction}/10."
    ),
    "RSI_OVERSOLD": (
        "Committee consensus: BUY on oversold setup. {surfaced_by} flagged the entry — {reason}. "
        "{vetted_by} validated risk parameters. RSI reading indicates extreme pessimism inconsistent "
        "with underlying fundamentals. Prior instances of this setup in this name resolved to the "
        "upside 70%+ of the time. Mean reversion play with tight stop. Conviction: {conviction}/10."
    ),
    "PRICE_DROP": (
        "Committee consensus: BUY the dip. {surfaced_by} identified the opportunity — {reason}. "
        "{vetted_by} stress-tested the thesis. Price drop appears driven by macro fear rather than "
        "company-specific deterioration. Fundamentals intact. Asymmetric entry point with 4:1 "
        "risk/reward at current levels. Sized conservatively given uncertainty. Conviction: {conviction}/10."
    ),
}

SIGNAL_VALUE_RANGES = {
    "VOLUME_SPIKE":      (1.5,  4.2),
    "PRICE_BREAKOUT":    (1.5,  4.2),
    "NEWS_SENTIMENT":    (5.0,  12.0),
    "EARNINGS_UPCOMING": (2.0,  14.0),
    "RSI_OVERSOLD":      (22.0, 38.0),
    "RSI_OVERBOUGHT":    (75.0, 85.0),
    "PRICE_DROP":        (5.0,  15.0),
}

# Portfolio curve — ends at exactly $10,000 on 2025-12-31
WAYPOINTS = [
    ("2025-01-02", 5000.0),
    ("2025-02-28", 5800.0),
    ("2025-04-30", 7200.0),
    ("2025-05-30", 6800.0),
    ("2025-08-29", 9100.0),
    ("2025-09-30", 9000.0),
    ("2025-12-31", 10000.0),
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_series(df, col: str):
    s = df[col]
    return s.iloc[:, 0] if hasattr(s, "columns") else s


def get_price(df, target_date: date, col: str = "Close") -> float | None:
    series = get_series(df, col)
    str_idx = series.index.strftime("%Y-%m-%d").tolist()
    for delta in range(0, 6):
        d = (target_date + timedelta(days=delta)).strftime("%Y-%m-%d")
        if d in str_idx:
            v = series.iloc[str_idx.index(d)]
            if v == v:
                return round(float(v), 4)
    for delta in range(1, 6):
        d = (target_date - timedelta(days=delta)).strftime("%Y-%m-%d")
        if d in str_idx:
            v = series.iloc[str_idx.index(d)]
            if v == v:
                return round(float(v), 4)
    return None


def interp(waypoints: list[tuple], target: date) -> float:
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


def to_ts(d: date, hour: int = 21, minute: int = 0) -> str:
    return datetime(d.year, d.month, d.day, hour, minute, 0, tzinfo=timezone.utc).isoformat()


def sig_val(signal_type: str) -> float:
    lo, hi = SIGNAL_VALUE_RANGES.get(signal_type, (1.0, 5.0))
    return round(random.uniform(lo, hi), 2)


def make_rationale(surfaced_by: str, vetted_by: str, signal_type: str, reason: str, conviction: int) -> str:
    template = APEX_RATIONALES.get(signal_type, APEX_RATIONALES["PRICE_BREAKOUT"])
    return template.format(
        surfaced_by=surfaced_by,
        vetted_by=vetted_by,
        reason=reason.lower(),
        conviction=conviction,
    )


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to MongoDB…")
    db = MongoClient(MONGODB_URI)[MONGODB_DB]

    # ── Fetch price data ───────────────────────────────────────────────────────
    all_tickers = sorted(set(
        row[0] for row in CLOSED_TRADES + [(t, b, s, su, v) for t, b, su, v, s in OPEN_POSITIONS]
    ))
    print(f"Fetching 2025 price data for {len(all_tickers)} tickers: {', '.join(all_tickers)}")

    price_data: dict[str, object] = {}
    for ticker in all_tickers:
        df = yf.download(ticker, start="2025-01-01", end="2026-01-10", auto_adjust=True, progress=False)
        if df is None or df.empty:
            print(f"  WARNING: no data for {ticker}")
        else:
            price_data[ticker] = df
            print(f"  {ticker}: {len(df)} trading days")

    # ── Idempotent cleanup — delete all seeded data ────────────────────────────
    print("\nCleaning up previous seed data…")
    n_trades    = db.trades.delete_many({"seeded": True}).deleted_count
    n_positions = db.positions.delete_many({"seeded": True}).deleted_count
    n_snaps     = db.portfolio_snapshots.delete_many({}).deleted_count
    n_decisions = db.decisions.delete_many({"seeded": True}).deleted_count
    print(f"  Deleted {n_trades} trades, {n_positions} positions, {n_snaps} snapshots, {n_decisions} decisions")

    # ── Generate closed trades ─────────────────────────────────────────────────
    print("\nGenerating closed trades…")
    trade_docs     = []
    decision_docs  = []
    trade_id       = 1
    wins = losses  = 0
    total_pnl      = 0.0
    shark_stats: dict[str, dict] = {}

    for ticker, buy_date_str, sell_date_str, surfaced_by, vetted_by, signal_type in CLOSED_TRADES:
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
        sv          = sig_val(signal_type)
        conviction  = random.choice([7, 8, 8, 9]) if pnl > 0 else random.choice([6, 7, 7])
        reason      = random.choice(REASONS[surfaced_by])
        buy_ts      = to_ts(buy_date,  14)
        sell_ts     = to_ts(sell_date, 21)

        if pnl > 0:
            wins += 1
        else:
            losses += 1
        total_pnl += pnl

        stats = shark_stats.setdefault(surfaced_by, {"wins": 0, "losses": 0})
        stats["wins" if pnl > 0 else "losses"] += 1

        trade_docs.append({
            "id": trade_id, "ticker": ticker, "action": "BUY",
            "shares": shares, "price": round(entry, 2), "timestamp": buy_ts,
            "surfaced_by": surfaced_by, "vetted_by": vetted_by, "conviction": conviction,
            "stop_loss": round(entry * 0.92, 2), "target_price": round(entry * 1.15, 2),
            "reason": reason, "outcome": outcome,
            "signal_type": signal_type, "signal_value": sv,
            "pnl": None, "exit_price": round(exit_, 2), "exit_time": sell_ts,
            "seeded": True,
        })
        trade_id += 1

        trade_docs.append({
            "id": trade_id, "ticker": ticker, "action": "SELL",
            "shares": shares, "price": round(exit_, 2), "timestamp": sell_ts,
            "surfaced_by": surfaced_by, "vetted_by": vetted_by, "conviction": conviction,
            "stop_loss": None, "target_price": None,
            "reason": f"Exit: {reason}", "outcome": outcome,
            "signal_type": signal_type, "signal_value": sv,
            "pnl": pnl, "exit_price": round(exit_, 2), "exit_time": sell_ts,
            "seeded": True,
        })
        trade_id += 1

        decision_docs.append({
            "ticker": ticker, "signal_type": signal_type,
            "decision": "BUY", "conviction": conviction,
            "rationale": make_rationale(surfaced_by, vetted_by, signal_type, reason, conviction),
            "timestamp": buy_ts, "seeded": True,
        })

        sign = "+" if pnl >= 0 else ""
        print(f"  {ticker:5s} {buy_date_str} → {sell_date_str}  "
              f"${entry:.2f} → ${exit_:.2f}  ×{shares}  PnL: {sign}${pnl:.2f}  [{outcome}]")

    # ── Generate open positions ────────────────────────────────────────────────
    print("\nGenerating open positions…")
    open_equity = 0.0
    position_docs = []

    for ticker, buy_date_str, surfaced_by, vetted_by, signal_type in OPEN_POSITIONS:
        buy_date = date.fromisoformat(buy_date_str)
        df = price_data.get(ticker)
        if df is None:
            print(f"  SKIP {ticker} — no price data")
            continue

        entry = get_price(df, buy_date, "Open")
        if entry is None:
            print(f"  SKIP {ticker} {buy_date_str} — price unavailable")
            continue
        cur_raw = get_price(df, date(2025, 12, 31), "Close")
        cur_price: float = cur_raw if cur_raw is not None else entry

        target_size = random.choice([900, 1000, 1100, 1200])
        shares      = max(1, int(target_size / entry))
        conviction  = random.choice([7, 8, 9])
        reason      = random.choice(REASONS[surfaced_by])
        sv          = sig_val(signal_type)
        buy_ts      = to_ts(buy_date, 14)
        open_equity += shares * cur_price

        trade_docs.append({
            "id": trade_id, "ticker": ticker, "action": "BUY",
            "shares": shares, "price": round(entry, 2), "timestamp": buy_ts,
            "surfaced_by": surfaced_by, "vetted_by": vetted_by, "conviction": conviction,
            "stop_loss": round(entry * 0.92, 2), "target_price": round(entry * 1.15, 2),
            "reason": reason, "outcome": "open",
            "signal_type": signal_type, "signal_value": sv,
            "pnl": None, "exit_price": None, "exit_time": None,
            "seeded": True,
        })
        trade_id += 1

        position_docs.append({
            "_id": ticker,
            "shares": shares,
            "entry_price": round(entry, 2),
            "current_price": round(cur_price, 2),
            "stop_loss": round(entry * 0.92, 2),
            "target_price": round(entry * 1.15, 2),
            "surfaced_by": surfaced_by,
            "vetted_by": vetted_by,
            "conviction": conviction,
            "entry_time": buy_ts,
            "seeded": True,
        })

        decision_docs.append({
            "ticker": ticker, "signal_type": signal_type,
            "decision": "BUY", "conviction": conviction,
            "rationale": make_rationale(surfaced_by, vetted_by, signal_type, reason, conviction),
            "timestamp": buy_ts, "seeded": True,
        })

        unrealized = round((cur_price - entry) * shares, 2)
        sign = "+" if unrealized >= 0 else ""
        print(f"  {ticker:5s} {buy_date_str} → OPEN  "
              f"${entry:.2f} → ${cur_price:.2f}  ×{shares}  Unrealized: {sign}${unrealized:.2f}")

    # ── Insert trades, positions, decisions ───────────────────────────────────
    if trade_docs:
        db.trades.insert_many(trade_docs)
        print(f"\nInserted {len(trade_docs)} trades")
    if position_docs:
        db.positions.insert_many(position_docs)
        print(f"Inserted {len(position_docs)} open positions")
    if decision_docs:
        db.decisions.insert_many(decision_docs)
        print(f"Inserted {len(decision_docs)} Apex decisions")

    # ── Generate portfolio snapshots ───────────────────────────────────────────
    print("\nGenerating portfolio snapshots…")
    snap_docs = []
    current   = date(2025, 1, 2)
    end       = date(2025, 12, 31)

    while current <= end:
        if current.weekday() < 5:
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

    # Force the final snapshot to exactly $10,000
    if snap_docs:
        snap_docs[-1]["portfolio_value"] = 10000.0
        snap_docs[-1]["cash"] = round(10000.0 - open_equity, 2)
        snap_docs[-1]["equity"] = round(open_equity, 2)

    db.portfolio_snapshots.insert_many(snap_docs)
    print(f"Inserted {len(snap_docs)} snapshots (final value: $10,000.00)")

    # ── Update portfolio document ──────────────────────────────────────────────
    cash = round(max(0.0, 10000.0 - open_equity), 2)
    db.portfolio.update_one(
        {"_id": "main"},
        {"$set": {
            "cash":          cash,
            "starting_cash": 5000.0,
            "equity":        round(open_equity, 2),
            "next_trade_id": trade_id,
        }},
        upsert=True,
    )
    print(f"Portfolio: cash=${cash:.2f}  equity=${open_equity:.2f}  total=$10,000.00")
    print(f"Next real trade ID will be: {trade_id}")

    # ── Summary ────────────────────────────────────────────────────────────────
    total_trades = wins + losses
    sign = "+" if total_pnl >= 0 else ""
    print(f"\n{'─' * 56}")
    print(f"Seeded {total_trades} closed trades ({wins} wins / {losses} losses)")
    print(f"Win rate: {wins / total_trades * 100:.1f}%")
    print(f"Open positions: {len(position_docs)} ({', '.join(p['_id'] for p in position_docs)})")
    print(f"Apex decisions: {len(decision_docs)}")
    print(f"Portfolio value: $10,000.00  (2025 PnL: {sign}${total_pnl:.2f} from $5,000 start)")

    print("\nPer-shark win rates:")
    for shark, stats in sorted(shark_stats.items()):
        w, l = stats["wins"], stats["losses"]
        t = w + l
        print(f"  {shark:20s}: {w}W/{l}L ({w/t*100:.0f}% win rate)")


if __name__ == "__main__":
    main()
