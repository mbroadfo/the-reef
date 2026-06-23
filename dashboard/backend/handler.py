"""The Reef Dashboard API — Lambda handler.

Routes:
  GET /api/portfolio    portfolio metrics + 90-day snapshots
  GET /api/positions    open positions
  GET /api/trades       trade history (limit, skip)
  GET /api/sharks       agent attribution leaderboard
  GET /api/decisions    recent Apex Shark rationale
  GET /api/trades/{id}  single trade + matching decision
  GET /api/sentiment    AI sentiment score 0-100 (Bullish/Neutral/Bearish)
  GET /api/sectors      sector ETF % changes (XLK, XLF, XLV, XLY, XLI, XLE)
  GET /api/nominations  active scanner nominations (< 48h TTL)
  GET /api/alpha        Reef vs SPY performance + Sharpe/win-rate stats
"""
from __future__ import annotations

import json
import os
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from pymongo import MongoClient, DESCENDING

_secrets: dict | None = None
_sector_cache: dict[str, str] = {}

# Hardcoded sectors for all reef watchlist tickers — avoids slow yf.info calls
_KNOWN_SECTORS: dict[str, str] = {
    "NVDA": "Technology",              "AMD": "Technology",
    "AVGO": "Technology",              "ARM": "Technology",
    "TSM": "Technology",               "SMCI": "Technology",
    "AAPL": "Technology",              "PLTR": "Technology",
    "META": "Communication Services",  "ASTS": "Communication Services",
    "COIN": "Financial Services",      "MSTR": "Financial Services",
    "MARA": "Financial Services",      "HOOD": "Financial Services",
    "TSLA": "Consumer Cyclical",       "RKLB": "Industrials",
    "SPCX": "Industrials",
}


def _get_sector(ticker: str) -> str:
    if ticker in _KNOWN_SECTORS:
        return _KNOWN_SECTORS[ticker]
    if ticker not in _sector_cache:
        try:
            import yfinance as yf
            info = yf.Ticker(ticker).info
            _sector_cache[ticker] = info.get("sector") or "Other"
        except Exception:
            _sector_cache[ticker] = "Other"
    return _sector_cache[ticker]


def _load_secrets() -> dict:
    global _secrets
    if _secrets is None:
        ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "us-west-2"))
        path = os.environ.get("SSM_SECRET_PATH", "/reef/prod/secrets")
        resp = ssm.get_parameter(Name=path, WithDecryption=True)
        _secrets = json.loads(resp["Parameter"]["Value"])
    assert _secrets is not None
    return _secrets


def _db():
    s = _load_secrets()
    client = MongoClient(s["MONGODB_URI"])
    return client[s.get("MONGODB_DB", "the_reef")]


def _ok(body: Any) -> dict:
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
        },
        "body": json.dumps(body, default=str),
    }


def _err(status: int, msg: str) -> dict:
    return {
        "statusCode": status,
        "headers": {"Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"error": msg}),
    }


# ── route handlers ────────────────────────────────────────────────────────────

def route_portfolio(db) -> dict:
    state = db.portfolio.find_one({"_id": "main"}) or {}
    cash = state.get("cash", 10000.0)
    starting = state.get("starting_cash", 10000.0)

    # Compute equity from live positions
    positions = list(db.positions.find())
    equity = sum(p["shares"] * p["current_price"] for p in positions)
    portfolio_value = cash + equity

    # Closed trade stats
    closed = [t for t in db.trades.find({"action": "SELL", "pnl": {"$ne": None}})]
    wins = [t for t in closed if (t.get("pnl") or 0.0) > 0]
    losses = [t for t in closed if (t.get("pnl") or 0.0) <= 0]
    total_realized = sum(t.get("pnl") or 0.0 for t in closed)
    win_sum = sum(t.get("pnl") or 0.0 for t in wins)
    loss_sum = sum(t.get("pnl") or 0.0 for t in losses)
    unrealized = sum((p["current_price"] - p["entry_price"]) * p["shares"] for p in positions)

    profit_factor = abs(win_sum / loss_sum) if loss_sum != 0 else None

    # Today / month gain
    today = datetime.now(timezone.utc).date()
    month_start = today.replace(day=1)

    def _parse_date(ts):
        try:
            if isinstance(ts, datetime):
                return ts.astimezone(timezone.utc).date()
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(timezone.utc).date()
        except Exception:
            return None

    today_gain = sum(
        t.get("pnl") or 0.0 for t in closed
        if _parse_date(t.get("timestamp")) == today
    )
    month_gain = sum(
        t.get("pnl") or 0.0 for t in closed
        if (_d := _parse_date(t.get("timestamp"))) is not None and _d >= month_start
    )

    # Active sharks — distinct normalized names across all trades
    raw_names = db.trades.distinct("surfaced_by")
    active_sharks = len({_LEGACY_SHARK_NAMES.get(n, n) for n in raw_names if n})

    # All snapshots chronologically — no limit so 1W/1M/3M timescale filters work correctly
    snaps = list(
        db.portfolio_snapshots.find({}, {"_id": 0})
        .sort("timestamp", 1)
    )

    # inception_date from first snapshot
    inception_date = str(snaps[0]["timestamp"])[:10] if snaps else ""

    # max single-trade gain
    max_trade_gain = max((t.get("pnl") or 0.0 for t in closed), default=0.0)

    # max drawdown from snapshot series (peak-to-trough %)
    max_drawdown = 0.0
    peak_val = snaps[0]["portfolio_value"] if snaps else starting
    for s in snaps:
        v = s["portfolio_value"]
        if v > peak_val:
            peak_val = v
        if peak_val > 0:
            dd = (peak_val - v) / peak_val * 100
            if dd > max_drawdown:
                max_drawdown = dd

    return _ok({
        "value": round(portfolio_value, 2),
        "cash": round(cash, 2),
        "equity": round(equity, 2),
        "starting_cash": round(starting, 2),
        "total_pnl": round(portfolio_value - starting, 2),
        "total_pnl_pct": round((portfolio_value - starting) / starting * 100, 2),
        "realized_pnl": round(total_realized, 2),
        "unrealized_pnl": round(unrealized, 2),
        "win_rate_pct": round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
        "total_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "today_gain": round(today_gain, 2),
        "today_gain_pct": round(today_gain / portfolio_value * 100, 2) if portfolio_value else 0.0,
        "month_gain": round(month_gain, 2),
        "month_gain_pct": round(month_gain / portfolio_value * 100, 2) if portfolio_value else 0.0,
        "active_sharks": active_sharks,
        "inception_date": inception_date,
        "max_trade_gain": round(max_trade_gain, 2),
        "max_drawdown": round(max_drawdown, 2),
        "snapshots": snaps,
    })


def route_positions(db) -> dict:
    from concurrent.futures import ThreadPoolExecutor
    docs = list(db.positions.find())

    # Pre-fetch all sectors in parallel
    tickers = [p["_id"] for p in docs]
    with ThreadPoolExecutor(max_workers=max(1, len(tickers))) as ex:
        sector_map = dict(zip(tickers, ex.map(_get_sector, tickers)))

    result = []
    for p in docs:
        entry = p["entry_price"]
        current = p["current_price"]
        shares = p["shares"]
        cost = entry * shares
        mv = current * shares
        pnl = mv - cost
        result.append({
            "ticker": p["_id"],
            "shares": shares,
            "entry_price": entry,
            "current_price": current,
            "stop_loss": p.get("stop_loss"),
            "target_price": p.get("target_price"),
            "unrealized_pnl": round(pnl, 2),
            "unrealized_pnl_pct": round(pnl / cost * 100, 2) if cost else 0.0,
            "cost_basis": round(cost, 2),
            "market_value": round(mv, 2),
            "surfaced_by": _norm_names(p.get("surfaced_by", "")),
            "vetted_by": _norm_names(p.get("vetted_by", "")),
            "conviction": p.get("conviction", 0),
            "entry_time": p.get("entry_time", ""),
            "sector": sector_map.get(p["_id"], "Other"),
        })
    result.sort(key=lambda x: x["unrealized_pnl"], reverse=True)
    return _ok(result)


def route_trades(db, limit: int = 50, skip: int = 0) -> dict:
    docs = list(db.trades.find().sort("id", DESCENDING).skip(skip).limit(limit))
    result = []

    for t in docs:
        result.append({
            "id": t["id"],
            "ticker": t["ticker"],
            "action": t["action"],
            "shares": t["shares"],
            "price": t["price"],
            "timestamp": t["timestamp"],
            "surfaced_by": _norm_names(t.get("surfaced_by", "")),
            "vetted_by": _norm_names(t.get("vetted_by", "")),
            "conviction": t.get("conviction", 0),
            "stop_loss": t.get("stop_loss"),
            "target_price": t.get("target_price"),
            "reason": t.get("reason", ""),
            "outcome": t.get("outcome", "open"),
            "pnl": t.get("pnl"),
            "exit_price": t.get("exit_price"),
            "exit_time": t.get("exit_time"),
        })
    total = db.trades.count_documents({})
    return _ok({"trades": result, "total": total, "skip": skip, "limit": limit})


def route_trade_detail(db, trade_id: int) -> dict:
    doc = db.trades.find_one({"id": trade_id})
    if not doc:
        return _err(404, f"Trade {trade_id} not found")

    trade = {
        "id": doc["id"],
        "ticker": doc["ticker"],
        "action": doc["action"],
        "shares": doc["shares"],
        "price": doc["price"],
        "timestamp": doc["timestamp"],
        "surfaced_by": _norm_names(doc.get("surfaced_by", "")),
        "vetted_by": _norm_names(doc.get("vetted_by", "")),
        "conviction": doc.get("conviction", 0),
        "stop_loss": doc.get("stop_loss"),
        "target_price": doc.get("target_price"),
        "reason": doc.get("reason", ""),
        "outcome": doc.get("outcome", "open"),
        "pnl": doc.get("pnl"),
        "exit_price": doc.get("exit_price"),
        "exit_time": doc.get("exit_time"),
    }

    # Find matching Apex decision (same ticker, nearest timestamp)
    decision = db.decisions.find_one(
        {"ticker": doc["ticker"]},
        sort=[("timestamp", DESCENDING)],
    )
    if decision:
        trade["apex_rationale"] = decision.get("rationale", "")
        trade["apex_decision"] = decision.get("decision", "")
        trade["apex_conviction"] = decision.get("conviction", 0)

    return _ok(trade)


_LEGACY_SHARK_NAMES: dict[str, str] = {
    # snake_case CrewAI agent names → display names
    "hunter_shark":     "Hunter Shark",
    "research_shark":   "Research Shark",
    "macro_shark":      "Macro Shark",
    "sentiment_shark":  "Sentiment Shark",
    "contrarian_shark": "Contrarian Shark",
    "risk_shark":       "Risk Shark",
    "wildcard_shark":   "Wildcard Shark",
    "apex_shark":       "Apex Shark",
    # legacy title-case renames
    "Fundamental Shark": "Research Shark",
    "Value Shark":       "Research Shark",
    "Earnings Shark":    "Research Shark",
    "Momentum Shark":    "Hunter Shark",
    "News Shark":        "Sentiment Shark",
    "Options Shark":     "Risk Shark",
}


def _norm_names(s: str) -> str:
    """Normalize a single name or comma-separated list of shark names."""
    if not s:
        return s
    return ", ".join(_LEGACY_SHARK_NAMES.get(p.strip(), p.strip()) for p in s.split(",") if p.strip())


def route_sharks(db) -> dict:
    scores: dict[str, list[float]] = defaultdict(list)

    for trade in db.trades.find({"action": "SELL", "pnl": {"$ne": None}}):
        pnl = trade.get("pnl") or 0.0
        surfaced = trade.get("surfaced_by", "")
        if surfaced:
            surfaced = _LEGACY_SHARK_NAMES.get(surfaced, surfaced)
            scores[surfaced].append(pnl)

    result = []
    for shark, pnls in scores.items():
        wins = sum(1 for p in pnls if p > 0)
        result.append({
            "name": shark,
            "trades": len(pnls),
            "total_pnl": round(sum(pnls), 2),
            "avg_pnl": round(sum(pnls) / len(pnls), 2),
            "win_rate": round(wins / len(pnls) * 100, 1) if pnls else 0.0,
        })

    result.sort(key=lambda x: x["total_pnl"], reverse=True)
    return _ok(result)


def route_decisions(db, limit: int = 10) -> dict:
    docs = list(db.decisions.find({}, {"_id": 0}).sort("timestamp", DESCENDING).limit(limit))
    return _ok(docs)


def route_sentiment(db) -> dict:
    closed = list(
        db.trades.find({"action": "SELL", "pnl": {"$ne": None}})
        .sort("id", DESCENDING)
        .limit(10)
    )

    if closed:
        recent_wins = sum(1 for t in closed if (t.get("pnl") or 0) > 0)
        win_score = (recent_wins / len(closed)) * 40
    else:
        win_score = 20

    state = db.portfolio.find_one({"_id": "main"}) or {}
    starting = state.get("starting_cash", 10000)
    positions = list(db.positions.find())
    cash = state.get("cash", starting)
    equity = sum(p["shares"] * p["current_price"] for p in positions)
    portfolio_value = cash + equity
    pnl_pct = (portfolio_value - starting) / starting * 100
    if pnl_pct > 5:
        trend_score = 30
    elif pnl_pct > 0:
        trend_score = 20
    elif pnl_pct > -5:
        trend_score = 10
    else:
        trend_score = 0

    pos_score = min(len(positions) * 6, 30)

    score = max(0, min(100, round(win_score + trend_score + pos_score)))

    if score >= 65:
        label = "Bullish"
    elif score >= 40:
        label = "Neutral"
    else:
        label = "Bearish"

    return _ok({
        "score": score,
        "label": label,
        "components": {
            "win_rate":  round(win_score),
            "trend":     round(trend_score),
            "positions": round(pos_score),
        },
    })


def _yf_pct(ticker: str) -> float:
    """Fetch day % change for a single ticker. Returns 0.0 on any error."""
    try:
        import yfinance as yf
        fi = yf.Ticker(ticker).fast_info
        prev = fi.previous_close
        curr = fi.last_price
        if prev and curr and prev > 0:
            return round(float((curr - prev) / prev * 100), 2)
        hist = yf.Ticker(ticker).history(period="5d")
        if len(hist) >= 2:
            return round(float((hist["Close"].iloc[-1] - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2] * 100), 2)
    except Exception as e:
        print(f"[yf_pct] {ticker}: {e}")
    return 0.0


def route_market(db) -> dict:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import yfinance as yf

    positions = list(db.positions.find())
    tickers = ["^VIX"] + [p["_id"] for p in positions]

    # Fetch all tickers in parallel
    pct_map: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=len(tickers)) as ex:
        futures = {ex.submit(_yf_pct, t): t for t in tickers}
        for f in as_completed(futures):
            pct_map[futures[f]] = f.result()

    vix_pct = pct_map.get("^VIX", 0.0)
    vix_data: dict = {"current": 0.0, "previous": 0.0, "pct_change": vix_pct}
    try:
        fi = yf.Ticker("^VIX").fast_info
        curr = fi.last_price
        prev = fi.previous_close
        if curr and prev and prev > 0:
            vix_data = {
                "current": round(float(curr), 2),
                "previous": round(float(prev), 2),
                "pct_change": round(float((curr - prev) / prev * 100), 2),
            }
    except Exception as e:
        print(f"[market] VIX detail error: {e}")

    holdings = []
    for p in positions:
        ticker = p["_id"]
        entry = p.get("entry_price", 0) or 0
        current = p.get("current_price", 0) or 0
        unrealized_pnl_pct = round((current - entry) / entry * 100, 2) if entry else 0.0
        holdings.append({
            "ticker": ticker,
            "daily_pct": pct_map.get(ticker, 0.0),
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "market_value": round(p.get("shares", 0) * current, 2),
            "sector": _get_sector(ticker),
        })

    holdings.sort(key=lambda x: x["market_value"], reverse=True)
    return _ok({"vix": vix_data, "holdings": holdings})


def route_nominations(db) -> dict:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=48)

    docs = list(
        db.nominations.find(
            {"created_at": {"$gte": cutoff}},
            {"_id": 0},
        ).sort("created_at", DESCENDING)
    )

    # Deduplicate — keep most recent nomination per ticker
    seen: set[str] = set()
    result = []
    for d in docs:
        ticker = d.get("ticker", "")
        if ticker in seen:
            continue
        seen.add(ticker)

        created = d["created_at"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        expires_in_hours = max(0.0, ((created + timedelta(hours=48)) - now).total_seconds() / 3600)
        result.append({
            "ticker":           ticker,
            "thesis":           d.get("thesis", ""),
            "source":           _norm_names(d.get("source", "")),
            "entry_range":      d.get("entry_range", ""),
            "created_at":       d.get("created_at"),
            "expires_in_hours": round(expires_in_hours, 1),
        })
        if len(result) >= 10:
            break

    return _ok(result)


def route_alpha(db) -> dict:
    import yfinance as yf

    def _snap_date(ts):
        try:
            if isinstance(ts, datetime):
                return ts.astimezone(timezone.utc).date()
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(timezone.utc).date()
        except Exception:
            return None

    snaps = list(db.portfolio_snapshots.find({}, {"_id": 0}).sort("timestamp", 1))

    # Group by date — last snapshot value per day
    date_value: dict = {}
    for s in snaps:
        d = _snap_date(s["timestamp"])
        if d:
            date_value[d] = s["portfolio_value"]

    sorted_dates = sorted(date_value.keys())

    _empty = {
        "reef_series": [], "spy_series": [], "alpha": None,
        "sharpe": None, "win_rate": None,
        "conviction_winners": None, "conviction_losers": None,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }

    if len(sorted_dates) < 2:
        return _ok(_empty)

    start_date, end_date = sorted_dates[0], sorted_dates[-1]

    # Fetch SPY daily closes
    spy_map: dict = {}
    try:
        hist = yf.Ticker("SPY").history(
            start=str(start_date - timedelta(days=5)),
            end=str(end_date + timedelta(days=2)),
        )
        for idx in hist.index:
            d = idx.date() if hasattr(idx, "date") else idx
            spy_map[d] = float(hist.loc[idx, "Close"])
    except Exception as e:
        print(f"[alpha] SPY fetch error: {e}")

    # SPY baseline: last trading day on or before start_date
    spy_base = None
    for d in sorted(spy_map):
        if d <= start_date:
            spy_base = spy_map[d]

    reef_base = date_value[sorted_dates[0]]
    reef_series = []
    spy_series  = []
    last_spy    = spy_base

    for d in sorted_dates:
        if d in spy_map:
            last_spy = spy_map[d]
        reef_series.append({"date": str(d), "value": round(date_value[d] / reef_base * 100, 2)})
        spy_val = round(last_spy / spy_base * 100, 2) if spy_base and last_spy else 100.0
        spy_series.append({"date": str(d), "value": spy_val})

    reef_total = (date_value[sorted_dates[-1]] / reef_base - 1) * 100
    spy_total  = (spy_series[-1]["value"] / 100 - 1) * 100 if spy_series else 0.0
    alpha      = round(reef_total - spy_total, 2)

    # Sharpe — meaningful only with ≥ 10 daily observations
    sharpe = None
    if len(sorted_dates) >= 10:
        daily_returns = [
            date_value[sorted_dates[i]] / date_value[sorted_dates[i - 1]] - 1
            for i in range(1, len(sorted_dates))
        ]
        std_r = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0.0
        if std_r > 0:
            sharpe = round(statistics.mean(daily_returns) / std_r * (252 ** 0.5), 2)

    # Win rate + conviction split from closed trades
    closed  = list(db.trades.find({"action": "SELL", "pnl": {"$ne": None}}))
    winners = [t for t in closed if (t.get("pnl") or 0) > 0]
    losers  = [t for t in closed if (t.get("pnl") or 0) <= 0]
    win_rate = round(len(winners) / len(closed) * 100, 1) if closed else None

    def _avg_conviction(trades):
        vals = [t.get("conviction") for t in trades if t.get("conviction")]
        return round(sum(vals) / len(vals), 1) if vals else None

    return _ok({
        "reef_series":         reef_series,
        "spy_series":          spy_series,
        "alpha":               alpha,
        "sharpe":              sharpe,
        "win_rate":            win_rate,
        "conviction_winners":  _avg_conviction(winners),
        "conviction_losers":   _avg_conviction(losers),
        "as_of":               datetime.now(timezone.utc).isoformat(),
    })


def route_sectors(db) -> dict:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    SECTOR_ETFS = {
        "Technology":        "XLK",
        "Financials":        "XLF",
        "Healthcare":        "XLV",
        "Consumer Cyclical": "XLY",
        "Industrials":       "XLI",
        "Energy":            "XLE",
    }

    with ThreadPoolExecutor(max_workers=len(SECTOR_ETFS)) as ex:
        futures = {ex.submit(_yf_pct, etf): (sector, etf) for sector, etf in SECTOR_ETFS.items()}
        results = {meta: f.result() for f, meta in [(f, futures[f]) for f in as_completed(futures)]}

    result = [
        {"sector": sector, "ticker": etf, "pct_change": results[(sector, etf)]}
        for sector, etf in SECTOR_ETFS.items()
    ]
    return _ok(result)


# ── router ────────────────────────────────────────────────────────────────────

def handler(event: dict, context) -> dict:
    method = (event.get("requestContext") or {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "/")
    qs = event.get("queryStringParameters") or {}

    if method == "OPTIONS":
        return _ok({})

    try:
        db = _db()
    except Exception as exc:
        return _err(500, f"DB connection failed: {exc}")

    try:
        if path == "/api/portfolio":
            return route_portfolio(db)
        elif path == "/api/positions":
            return route_positions(db)
        elif path == "/api/trades":
            limit = min(int(qs.get("limit", 50)), 200)
            skip = int(qs.get("skip", 0))
            return route_trades(db, limit, skip)
        elif path.startswith("/api/trades/"):
            trade_id = int(path.split("/")[-1])
            return route_trade_detail(db, trade_id)
        elif path == "/api/sharks":
            return route_sharks(db)
        elif path == "/api/decisions":
            return route_decisions(db)
        elif path == "/api/sentiment":
            return route_sentiment(db)
        elif path == "/api/sectors":
            return route_sectors(db)
        elif path == "/api/market":
            return route_market(db)
        elif path == "/api/nominations":
            return route_nominations(db)
        elif path == "/api/alpha":
            return route_alpha(db)
        else:
            return _err(404, f"No route: {path}")
    except Exception as exc:
        return _err(500, str(exc))
