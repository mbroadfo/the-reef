"""
Shark audit — nominations vs executions breakdown.
Shows which sharks are generating nominations and which picks are actually being traded.
"""
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient, DESCENDING

uri = os.environ["MONGODB_URI"]
db_name = os.environ.get("MONGODB_DB", "the_reef")
db = MongoClient(uri).get_database(db_name)

now = datetime.now(timezone.utc)

# ── Nominations ───────────────────────────────────────────────────────────────
all_noms = list(db.nominations.find({}, {"_id": 0}).sort("created_at", DESCENDING))
recent_noms = [n for n in all_noms if (now - n["created_at"].replace(tzinfo=timezone.utc) if n["created_at"].tzinfo is None else now - n["created_at"]) < timedelta(hours=48)]

print(f"=== NOMINATIONS ({len(all_noms)} total, {len(recent_noms)} last 48h) ===")
src_counts = Counter(n.get("source", "unknown") for n in all_noms)
for src, cnt in src_counts.most_common():
    print(f"  {src}: {cnt} nominations")

src_tickers = defaultdict(list)
for n in all_noms:
    src_tickers[n.get("source", "unknown")].append(n.get("ticker", "?"))
print("\nTickers nominated per source:")
for src, tickers in sorted(src_tickers.items()):
    uniq = sorted(set(tickers))
    print(f"  {src}: {uniq}")

# ── Trades ────────────────────────────────────────────────────────────────────
trades = list(db.trades.find({}, {"_id": 0}).sort("timestamp", DESCENDING))
print(f"\n=== TRADES ({len(trades)} total) ===")
trade_tickers = [t.get("ticker") for t in trades]
buy_tickers = [t.get("ticker") for t in trades if t.get("action") == "BUY"]

print(f"  BUYs: {buy_tickers}")

# Which nominated tickers actually got traded?
nom_tickers = set(n.get("ticker") for n in all_noms)
traded_tickers = set(trade_tickers)
executed = nom_tickers & traded_tickers
never_traded = nom_tickers - traded_tickers

print(f"\n=== CONVERSION ===")
print(f"  Nominated tickers: {sorted(nom_tickers)}")
print(f"  Traded tickers: {sorted(traded_tickers)}")
print(f"  Executed from nominations: {sorted(executed)}")
print(f"  Nominated but never traded: {sorted(never_traded)}")

# P&L on closed trades
sells = [t for t in trades if t.get("action") == "SELL" and t.get("pnl") is not None]
if sells:
    print(f"\n=== CLOSED TRADE P&L ===")
    for t in sells:
        print(f"  SELL {t['ticker']}: ${t['pnl']:.2f} @ {t.get('timestamp','?')[:16]}")
    total_closed_pnl = sum(t["pnl"] for t in sells)
    print(f"  Total closed P&L: ${total_closed_pnl:.2f}")

# Active sharks by nomination volume (last 7 days)
week_ago = now - timedelta(days=7)
week_noms = [n for n in all_noms if (n["created_at"].replace(tzinfo=timezone.utc) if n["created_at"].tzinfo is None else n["created_at"]) >= week_ago]
print(f"\n=== SHARK ACTIVITY (last 7 days) ===")
week_src = Counter(n.get("source", "unknown") for n in week_noms)
for src, cnt in week_src.most_common():
    print(f"  {src}: {cnt} nominations")
dormant = {"Hunter Shark", "Research Shark", "Macro Shark", "Sentiment Shark", "Contrarian Shark", "Risk Shark", "Wildcard Shark"} - set(week_src.keys())
if dormant:
    print(f"  DORMANT (0 nominations): {sorted(dormant)}")
