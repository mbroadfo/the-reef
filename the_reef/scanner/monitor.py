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
    "EARNINGS_UPCOMING": 10,    # Earnings within 7 days
    "VOLUME_SPIKE":       9,    # Volume > 2.5x 20-day avg
    "PRICE_BREAKOUT":     8,    # Price change > 4% in one day
    "RSI_OVERSOLD":       6,    # RSI < 28 — potential reversal
    "RSI_OVERBOUGHT":     5,    # RSI > 75 — potential short opportunity
    "PRICE_DROP":         7,    # Price drop > 4% — possible entry or stop review
}

DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "META", "AMZN", "GOOGL", "TSLA",
    "AMD", "PLTR", "RKLB", "SMCI", "ARM", "SPY", "QQQ",
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
    if dte is not None and 0 < dte <= 7:
        signals.append(ScanSignal(ticker, "EARNINGS_UPCOMING", SIGNAL_TYPES["EARNINGS_UPCOMING"], dte, price, now))

    return signals


def run_scan(watchlist: list[str] = DEFAULT_WATCHLIST) -> list[ScanSignal]:
    """Scan all tickers. Returns signals sorted by priority (highest first)."""
    all_signals: list[ScanSignal] = []
    for ticker in watchlist:
        try:
            ticker_signals = scan_ticker(ticker)
            all_signals.extend(ticker_signals)
        except Exception as e:
            print(f"[scanner] Error scanning {ticker}: {e}")

    return sorted(all_signals, key=lambda s: s.priority, reverse=True)


def save_signals(signals: list[ScanSignal]):
    """Persist signals to MongoDB signals collection."""
    try:
        from ..brokerage.the_tank import get_db
        db = get_db()
        if signals:
            db.signals.insert_many([s.to_dict() for s in signals])
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
        docs = list(db.signals.find().sort("timestamp", -1).limit(limit))
        return [ScanSignal.from_dict({k: v for k, v in d.items() if k != "_id"}) for d in docs]
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


if __name__ == "__main__":
    # Run a single scan and print results — useful for GitHub Actions
    import sys

    watchlist_arg = sys.argv[1].split(",") if len(sys.argv) > 1 else DEFAULT_WATCHLIST
    signals = run_scan(watchlist_arg)
    save_signals(signals)

    if signals:
        print(f"SIGNALS_FOUND=true")
        print(f"SIGNAL_COUNT={len(signals)}")
        for s in signals:
            print(f"  {s.signal_type}: {s.ticker} @ ${s.price:.2f}")
        sys.exit(0)
    else:
        print("SIGNALS_FOUND=false")
        sys.exit(0)
