"""
MongoDB data audit — verifies data integrity across all collections
and cross-checks what the dashboard API would compute vs raw data.
Run via: gh workflow run tools-db-audit.yml
"""
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

from pymongo import MongoClient, DESCENDING

MONGODB_URI = os.environ["MONGODB_URI"]
MONGODB_DB = os.environ.get("MONGODB_DB", "the_reef")

client = MongoClient(MONGODB_URI)
db = client[MONGODB_DB]

issues: list[str] = []
warnings: list[str] = []


def flag(msg: str):
    issues.append(f"  [FAIL] {msg}")
    print(f"  [FAIL] {msg}")


def warn(msg: str):
    warnings.append(f"  [WARN] {msg}")
    print(f"  [WARN] {msg}")


def ok(msg: str):
    print(f"  [ OK ] {msg}")


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── 1. Collection counts ───────────────────────────────────────────────────────
section("1. COLLECTION COUNTS")
for coll in ["trades", "positions", "portfolio", "portfolio_snapshots", "decisions", "signals"]:
    n = db[coll].count_documents({})
    ok(f"{coll}: {n} docs")


# ── 2. Portfolio state ─────────────────────────────────────────────────────────
section("2. PORTFOLIO STATE")
state = db.portfolio.find_one({"_id": "main"})
if not state:
    flag("No portfolio document found (missing _id='main')")
else:
    cash = state.get("cash", 0)
    starting = state.get("starting_cash", 10000)
    ok(f"cash=${cash:.2f}  starting=${starting:.2f}")
    if cash < 0:
        flag(f"Negative cash balance: ${cash:.2f}")


# ── 3. Trades audit ───────────────────────────────────────────────────────────
section("3. TRADES AUDIT")
all_trades = list(db.trades.find().sort("id", 1))
ok(f"Total trades: {len(all_trades)}")

REQUIRED_FIELDS = ["id", "ticker", "action", "shares", "price", "timestamp"]
VALID_ACTIONS = {"BUY", "SELL"}
ids_seen: set[int] = set()

buys: dict[str, list] = defaultdict(list)
sells: dict[str, list] = defaultdict(list)

for t in all_trades:
    tid = t.get("id")
    ticker = t.get("ticker", "?")
    action = t.get("action", "?")

    # Duplicate IDs
    if tid in ids_seen:
        flag(f"Duplicate trade id={tid} ticker={ticker}")
    ids_seen.add(tid)

    # Required fields
    for f in REQUIRED_FIELDS:
        if f not in t or t[f] is None:
            flag(f"Trade id={tid} missing field '{f}'")

    # Valid action
    if action not in VALID_ACTIONS:
        flag(f"Trade id={tid} has invalid action='{action}'")

    # Shares must be positive integer
    shares = t.get("shares")
    if not isinstance(shares, int) or shares <= 0:
        flag(f"Trade id={tid} ({ticker} {action}): shares={shares!r} — must be positive int")

    # Price sanity
    price = t.get("price", 0)
    if price <= 0:
        flag(f"Trade id={tid} ({ticker} {action}): price={price} <= 0")

    # SELL must have pnl
    if action == "SELL":
        pnl = t.get("pnl")
        if pnl is None:
            flag(f"Trade id={tid} SELL {ticker}: pnl is None (not computed)")
        exit_price = t.get("exit_price")
        if exit_price is None:
            warn(f"Trade id={tid} SELL {ticker}: exit_price is None")

    # conviction range (used as 0-10 scale, displayed as *10%)
    conviction = t.get("conviction", 0)
    if conviction is not None and not (0 <= conviction <= 10):
        warn(f"Trade id={tid} ({ticker}): conviction={conviction} outside 0-10 range")

    # surfaced_by populated?
    if not t.get("surfaced_by"):
        warn(f"Trade id={tid} ({ticker} {action}): surfaced_by is empty")

    # Accumulate for BUY/SELL matching
    if action == "BUY":
        buys[ticker].append(t)
    elif action == "SELL":
        sells[ticker].append(t)


# ── 4. BUY/SELL pairing ───────────────────────────────────────────────────────
section("4. BUY/SELL PAIRING")
all_tickers = set(buys) | set(sells)
for ticker in sorted(all_tickers):
    b = len(buys[ticker])
    s = len(sells[ticker])
    if s > b:
        flag(f"{ticker}: {s} SELLs but only {b} BUYs (oversell)")
    elif b > s:
        # Check if there's an open position
        pos = db.positions.find_one({"_id": ticker})
        if pos:
            ok(f"{ticker}: {b} BUYs, {s} SELLs — {b-s} open position(s) confirmed")
        else:
            warn(f"{ticker}: {b} BUYs, {s} SELLs — no open position record in positions collection")
    else:
        ok(f"{ticker}: {b} BUYs, {s} SELLs — balanced")


# ── 5. Positions vs trades consistency ────────────────────────────────────────
section("5. POSITIONS vs TRADES")
positions = list(db.positions.find())
ok(f"Open positions: {len(positions)}")

for p in positions:
    ticker = p["_id"]
    shares_pos = p.get("shares", 0)
    entry_price = p.get("entry_price", 0)
    current_price = p.get("current_price", 0)

    if shares_pos <= 0:
        flag(f"Position {ticker}: shares={shares_pos} <= 0")
    if entry_price <= 0:
        flag(f"Position {ticker}: entry_price={entry_price} <= 0")
    if current_price <= 0:
        warn(f"Position {ticker}: current_price={current_price} — stale price?")

    # Net shares from trades
    bought = sum(t["shares"] for t in buys.get(ticker, []))
    sold = sum(t["shares"] for t in sells.get(ticker, []))
    net_from_trades = bought - sold
    if net_from_trades != shares_pos:
        flag(f"Position {ticker}: position.shares={shares_pos} but trades net={net_from_trades} (bought={bought}, sold={sold})")
    else:
        ok(f"Position {ticker}: shares={shares_pos} matches trade history")

    # Check entry_price vs first BUY price
    if ticker in buys:
        first_buy_price = buys[ticker][0].get("price", 0)
        if abs(entry_price - first_buy_price) > 0.01:
            warn(f"Position {ticker}: entry_price={entry_price} vs first BUY price={first_buy_price}")


# ── 6. Portfolio value cross-check ────────────────────────────────────────────
section("6. PORTFOLIO VALUE CROSS-CHECK")
if state:
    cash = state.get("cash", 0)
    equity = sum(p["shares"] * p["current_price"] for p in positions)
    live_value = cash + equity
    ok(f"Cash=${cash:.2f}  Equity=${equity:.2f}  Live value=${live_value:.2f}")

    # Latest snapshot
    latest_snap = db.portfolio_snapshots.find_one({}, sort=[("timestamp", DESCENDING)])
    if latest_snap:
        snap_value = latest_snap["portfolio_value"]
        diff = abs(live_value - snap_value)
        if diff > 500:
            warn(f"Live value ${live_value:.2f} vs latest snapshot ${snap_value:.2f} — diff=${diff:.2f} (market moved or stale prices)")
        else:
            ok(f"Latest snapshot=${snap_value:.2f} — within ${diff:.2f} of live value")

    # Cash math cross-check: starting + realized - cost_of_open_positions ≈ cash
    closed = [t for t in all_trades if t.get("action") == "SELL" and t.get("pnl") is not None]
    total_realized = sum(t.get("pnl", 0) for t in closed)
    open_cost = sum(
        b["shares"] * b["price"]
        for ticker in buys
        for b in buys[ticker]
        if any(p["_id"] == ticker for p in positions)
    )
    starting = state.get("starting_cash", 10000)
    expected_cash = starting + total_realized - open_cost
    cash_diff = abs(cash - expected_cash)
    if cash_diff > 10:
        warn(f"Cash mismatch: actual=${cash:.2f}, expected=${expected_cash:.2f} "
             f"(starting={starting:.2f} + realized={total_realized:.2f} - open_cost={open_cost:.2f}), diff=${cash_diff:.2f}")
    else:
        ok(f"Cash math checks out: ${cash:.2f} ≈ starting + realized - open_cost")
    ok(f"Total realized PnL from SELLs: ${total_realized:.2f}")
    ok(f"Wins: {len([t for t in closed if t.get('pnl',0)>0])}  Losses: {len([t for t in closed if t.get('pnl',0)<=0])}")


# ── 7. Snapshots audit ────────────────────────────────────────────────────────
section("7. PORTFOLIO SNAPSHOTS")
snaps = list(db.portfolio_snapshots.find({}, {"_id": 0}).sort("timestamp", 1))
ok(f"Total snapshots: {len(snaps)}")
if snaps:
    ok(f"First: {str(snaps[0]['timestamp'])[:19]}  value=${snaps[0]['portfolio_value']:.2f}")
    ok(f"Last:  {str(snaps[-1]['timestamp'])[:19]}  value=${snaps[-1]['portfolio_value']:.2f}")
    # Check for nulls
    null_vals = [s for s in snaps if s.get("portfolio_value") is None]
    if null_vals:
        flag(f"{len(null_vals)} snapshots have null portfolio_value")
    # Check for negative values
    neg_vals = [s for s in snaps if (s.get("portfolio_value") or 0) < 0]
    if neg_vals:
        flag(f"{len(neg_vals)} snapshots have negative portfolio_value")
    # Check event types
    events = defaultdict(int)
    for s in snaps:
        events[s.get("event", "unknown")] += 1
    for evt, cnt in sorted(events.items()):
        ok(f"  event='{evt}': {cnt}")


# ── 8. Dashboard API simulation ───────────────────────────────────────────────
section("8. DASHBOARD METRICS (simulated)")
closed = [t for t in all_trades if t.get("action") == "SELL" and t.get("pnl") is not None]
wins = [t for t in closed if (t.get("pnl") or 0) > 0]
losses = [t for t in closed if (t.get("pnl") or 0) <= 0]
win_rate = round(len(wins) / len(closed) * 100, 1) if closed else 0.0
ok(f"Win rate: {win_rate}%  ({len(wins)} wins / {len(closed)} closed trades)")

active_sharks_count = len(db.trades.distinct("surfaced_by"))
shark_names = db.trades.distinct("surfaced_by")
ok(f"Active sharks ({active_sharks_count}): {shark_names}")

today = datetime.now(timezone.utc).date()
today_closed = [t for t in closed if str(t.get("timestamp", ""))[:10] == str(today)]
ok(f"Today's closed trades: {len(today_closed)}  PnL: ${sum(t.get('pnl',0) for t in today_closed):.2f}")

# conviction field distribution
convictions = [t.get("conviction") for t in all_trades if t.get("conviction") is not None]
if convictions:
    ok(f"Conviction range: min={min(convictions)} max={max(convictions)} — displayed as *10% in confidence badge")


# ── 9. Decisions collection ───────────────────────────────────────────────────
section("9. DECISIONS COLLECTION")
total_decisions = db.decisions.count_documents({})
decisions = list(db.decisions.find({}, {"_id": 0}).sort("timestamp", DESCENDING).limit(5))
ok(f"Total decisions: {total_decisions}")
if total_decisions == 0:
    warn("No decisions — TradeDetails Apex rationale will be blank for all trades")
for d in decisions:
    ok(f"  {str(d.get('timestamp',''))[:19]}  {d.get('ticker','?')}  {d.get('decision','?')}  conviction={d.get('conviction','?')}")


# ── 10. Sample trades (first 5 + last 5) ─────────────────────────────────────
section("10. SAMPLE TRADES")
print("  --- Most recent 5 ---")
for t in list(db.trades.find().sort("id", DESCENDING).limit(5)):
    pnl_str = f"  pnl=${t.get('pnl'):.2f}" if t.get("pnl") is not None else ""
    print(f"  id={t['id']}  {t['action']} {t.get('shares')}x {t['ticker']} @${t.get('price'):.2f}  surfaced_by={t.get('surfaced_by','')}  conviction={t.get('conviction')}{pnl_str}")
print("  --- Oldest 5 ---")
for t in list(db.trades.find().sort("id", 1).limit(5)):
    pnl_str = f"  pnl=${t.get('pnl'):.2f}" if t.get("pnl") is not None else ""
    print(f"  id={t['id']}  {t['action']} {t.get('shares')}x {t['ticker']} @${t.get('price'):.2f}  surfaced_by={t.get('surfaced_by','')}  conviction={t.get('conviction')}{pnl_str}")


# ── Summary ───────────────────────────────────────────────────────────────────
section("SUMMARY")
if issues:
    print(f"\n  FAILURES ({len(issues)}):")
    for i in issues:
        print(i)
if warnings:
    print(f"\n  WARNINGS ({len(warnings)}):")
    for w in warnings:
        print(w)
if not issues and not warnings:
    print("  All checks passed — data looks clean.")
elif not issues:
    print(f"  No failures. {len(warnings)} warnings to review.")
else:
    print(f"\n  {len(issues)} failure(s), {len(warnings)} warning(s)")
    sys.exit(1)
