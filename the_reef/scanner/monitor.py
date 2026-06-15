"""Lightweight scanner — no LLM, pure math against yfinance.

Runs continuously (locally) or on cron (GitHub Actions).
Emits ScanSignal objects that trigger the deep-dive crew.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from ..tools.market_data import (
    get_price, get_volume_ratio, get_rsi,
    get_price_change_pct, days_to_earnings,
)

# Signals ordered by excitement level — higher = more interesting
SIGNAL_TYPES = {
    "EARNINGS_UPCOMING": 10,    # Earnings within 14 days
    "VOLUME_SPIKE":       9,    # Volume > 2.5x 20-day avg
    "PRICE_BREAKOUT":     8,    # Price change > 4% in one day
    "NEWS_SENTIMENT":     8,    # 5-day trend diverges from 1-day (news-driven move)
    "RSI_OVERSOLD":       6,    # RSI < 28 — potential reversal
    "RSI_OVERBOUGHT":     5,    # RSI > 75 — potential short opportunity
    "PRICE_DROP":         7,    # Price drop > 4% — possible entry or stop review
}

DEFAULT_WATCHLIST = [
    # Tech / AI / semis  → hunter_shark + research_shark
    "NVDA", "AMD", "AVGO", "ARM", "TSM", "META", "PLTR",
    # Crypto-correlated  → wildcard_shark
    "COIN", "MSTR", "MARA", "HOOD",
    # Special situations → wildcard_shark
    "RKLB", "ASTS", "TSLA", "SMCI",
]

SIGNALS_FILE = Path(__file__).parent.parent.parent / "data" / "scan_signals.json"


@dataclass
class ScanSignal:
    ticker: str
    signal_type: str
    priority: int
    value: float          # The triggering value (volume ratio, RSI, change%, etc.)
    price: float
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ScanSignal":
        return cls(**d)


def scan_ticker(ticker: str) -> list[ScanSignal]:
    """Run all threshold checks on a single ticker. Returns any triggered signals."""
    signals: list[ScanSignal] = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    price = get_price(ticker)
    if price is None:
        return signals

    # Volume spike
    vol_ratio = get_volume_ratio(ticker)
    if vol_ratio is not None and vol_ratio >= 2.5:
        signals.append(ScanSignal(ticker, "VOLUME_SPIKE", SIGNAL_TYPES["VOLUME_SPIKE"], vol_ratio, price, now))

    # RSI
    rsi = get_rsi(ticker)
    if rsi is not None:
        if rsi <= 28:
            signals.append(ScanSignal(ticker, "RSI_OVERSOLD", SIGNAL_TYPES["RSI_OVERSOLD"], rsi, price, now))
        elif rsi >= 75:
            signals.append(ScanSignal(ticker, "RSI_OVERBOUGHT", SIGNAL_TYPES["RSI_OVERBOUGHT"], rsi, price, now))

    # Big intraday move
    change = get_price_change_pct(ticker)
    if change is not None:
        if change >= 4.0:
            signals.append(ScanSignal(ticker, "PRICE_BREAKOUT", SIGNAL_TYPES["PRICE_BREAKOUT"], change, price, now))
        elif change <= -4.0:
            signals.append(ScanSignal(ticker, "PRICE_DROP", SIGNAL_TYPES["PRICE_DROP"], abs(change), price, now))

    # Earnings coming up
    dte = days_to_earnings(ticker)
    if dte is not None and 0 < dte <= 14:
        signals.append(ScanSignal(ticker, "EARNINGS_UPCOMING", SIGNAL_TYPES["EARNINGS_UPCOMING"], dte, price, now))

    # News sentiment — 5-day momentum diverging from today = news-driven move
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="6d")
        if len(hist) >= 5:
            five_day_chg = (
                (hist["Close"].iloc[-1] - hist["Close"].iloc[-5])
                / hist["Close"].iloc[-5] * 100
            )
            if abs(five_day_chg) > 5.0 and change is not None and abs(change) < 2.0:
                signals.append(ScanSignal(
                    ticker, "NEWS_SENTIMENT",
                    SIGNAL_TYPES["NEWS_SENTIMENT"],
                    five_day_chg, price, now
                ))
    except Exception:
        pass

    return signals


def get_dynamic_tickers(count: int = 25) -> list[str]:
    """Pull top movers from yfinance screener — no auth required, no extra cost."""
    import yfinance as yf
    tickers: set[str] = set()
    for screen_name in ("day_gainers", "day_losers", "most_actives"):
        try:
            result = yf.screen(screen_name, count=count)
            for quote in result.get("quotes", []):
                sym = quote.get("symbol", "")
                if sym and "." not in sym and "-" not in sym and len(sym) <= 5:
                    tickers.add(sym)
        except Exception as e:
            print(f"[scanner] Screener '{screen_name}' unavailable: {e}")
    return sorted(tickers)


def run_scan(watchlist: list[str] = DEFAULT_WATCHLIST, include_movers: bool = True) -> list[ScanSignal]:
    """Scan all tickers. Returns signals sorted by priority (highest first)."""
    effective = list(watchlist)
    if include_movers:
        dynamic = get_dynamic_tickers()
        added = [t for t in dynamic if t not in effective]
        if added:
            print(f"[scanner] +{len(added)} dynamic movers: {', '.join(added)}")
            effective = effective + added
    print(f"[scanner] Scanning {len(effective)} tickers ({len(watchlist)} static + {len(effective) - len(watchlist)} dynamic)")

    all_signals: list[ScanSignal] = []
    for ticker in effective:
        try:
            ticker_signals = scan_ticker(ticker)
            all_signals.extend(ticker_signals)
        except Exception as e:
            print(f"[scanner] Error scanning {ticker}: {e}")

    return sorted(all_signals, key=lambda s: s.priority, reverse=True)


def save_signals(signals: list[ScanSignal]):
    """Persist signals to MongoDB signals collection.

    Deduplicates: skips any ticker+signal_type seen in the last hour.
    TTL index auto-expires documents after 24 hours.
    """
    from datetime import timedelta
    try:
        from ..brokerage.the_tank import get_db
        db = get_db()

        # Ensure TTL index exists (idempotent)
        db.signals.create_index("created_at", expireAfterSeconds=86400)

        if not signals:
            return

        # Fetch all (ticker, signal_type) pairs written in the last hour
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        recent = {
            (d["ticker"], d["signal_type"])
            for d in db.signals.find(
                {"created_at": {"$gte": cutoff}},
                {"ticker": 1, "signal_type": 1},
            )
        }

        now = datetime.now(timezone.utc)
        new_docs = [
            {"created_at": now, **s.to_dict()}
            for s in signals
            if (s.ticker, s.signal_type) not in recent
        ]
        if new_docs:
            db.signals.insert_many(new_docs)
            print(f"[scanner] Saved {len(new_docs)} new signal(s) — {len(signals) - len(new_docs)} duplicate(s) skipped")
        else:
            print(f"[scanner] All {len(signals)} signal(s) already recorded in the last hour — skipping")
    except Exception as e:
        # Fallback to local file if MongoDB not available
        SIGNALS_FILE.parent.mkdir(exist_ok=True)
        SIGNALS_FILE.write_text(json.dumps([s.to_dict() for s in signals], indent=2))
        print(f"[scanner] MongoDB unavailable ({e}), wrote signals to {SIGNALS_FILE}")


def load_signals(limit: int = 20) -> list[ScanSignal]:
    """Load most recent signals from MongoDB."""
    try:
        from ..brokerage.the_tank import get_db
        db = get_db()
        docs = list(db.signals.find().sort("created_at", -1).limit(limit))
        return [ScanSignal.from_dict({k: v for k, v in d.items() if k not in ("_id", "created_at")}) for d in docs]
    except Exception:
        # Fallback to local file
        if SIGNALS_FILE.exists():
            return [ScanSignal.from_dict(d) for d in json.loads(SIGNALS_FILE.read_text())]
        return []


def is_market_hours() -> bool:
    now = datetime.now(timezone.utc)
    # NYSE: 9:30am–4:00pm ET = 14:30–21:00 UTC (EST) / 13:30–20:00 UTC (EDT)
    # Approximate — good enough for scanner scheduling
    if now.weekday() >= 5:  # Saturday, Sunday
        return False
    hour, minute = now.hour, now.minute
    # Use 13:30–21:00 UTC to cover both EST and EDT
    return (hour > 13 or (hour == 13 and minute >= 30)) and hour < 21


def start_monitor(
    watchlist: list[str] = DEFAULT_WATCHLIST,
    on_signal: Optional[Callable[[list[ScanSignal]], None]] = None,
    interval_secs: int = 300,
):
    """Run scanner in a loop — for local continuous monitoring."""
    print(f"[The Reef] Scanner started | watching {len(watchlist)} tickers | interval {interval_secs}s")
    while True:
        if is_market_hours():
            print(f"[scanner] Scanning {len(watchlist)} tickers...")
            signals = run_scan(watchlist)
            if signals:
                save_signals(signals)
                print(f"[scanner] {len(signals)} signal(s) detected:")
                for s in signals:
                    print(f"  🦈 {s.signal_type} — {s.ticker} @ ${s.price:.2f} (value: {s.value:.2f})")
                if on_signal:
                    on_signal(signals)
            else:
                print("[scanner] No signals this cycle.")
        else:
            print("[scanner] Market closed — sleeping.")
        time.sleep(interval_secs)


class ReefMonitor:
    """Thin wrapper exposing scanner config as instance attributes."""
    SIGNAL_TYPES = SIGNAL_TYPES
    watchlist = DEFAULT_WATCHLIST

    def scan(self) -> list[ScanSignal]:
        return run_scan(self.watchlist)


if __name__ == "__main__":
    # Run a single scan and print results — used by scanner.yml GitHub Actions
    import sys
    from datetime import timedelta

    watchlist_arg = sys.argv[1].split(",") if len(sys.argv) > 1 else DEFAULT_WATCHLIST
    signals = run_scan(watchlist_arg)
    save_signals(signals)

    if signals:
        print(f"SIGNALS_FOUND=true")
        print(f"SIGNAL_COUNT={len(signals)}")
        for s in signals:
            print(f"  {s.signal_type}: {s.ticker} @ ${s.price:.2f}")

        # Find best dispatch candidate — skip tickers already held or dived in last 4h
        candidate = None
        try:
            from ..brokerage.the_tank import TheTank, get_db
            tank = TheTank()
            db = get_db()
            open_tickers = set(tank.positions.keys())
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
            recently_dived = {
                d["ticker"] for d in db.decisions.find({"timestamp": {"$gte": cutoff}})
            }
            blocked = open_tickers | recently_dived
            for s in signals:
                if s.ticker not in blocked:
                    candidate = s
                    break
            if blocked:
                print(f"[scanner] Dispatch blocked for: {', '.join(blocked)}")
        except Exception as e:
            print(f"[scanner] Guard check failed ({e}) — using top signal")
            candidate = signals[0]

        if candidate:
            print(f"TOP_TICKER={candidate.ticker}")
            print(f"TOP_PRIORITY={candidate.priority}")
            print(f"TOP_SIGNAL={candidate.signal_type}")
        else:
            print("TOP_TICKER=")
            print("TOP_PRIORITY=0")
            print("TOP_SIGNAL=")
        sys.exit(0)
    else:
        print("SIGNALS_FOUND=false")
        sys.exit(0)
