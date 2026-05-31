#!/usr/bin/env python
"""The Reef — entry point.

Usage:
  python main.py scan           # Run one scanner cycle and print signals
  python main.py monitor        # Run scanner continuously (local mode)
  python main.py dive NVDA      # Run full shark panel on a specific ticker
  python main.py stops          # Check all open positions for stop-loss breaches
  python main.py dashboard      # Launch live Rich terminal dashboard
  python main.py report         # Print performance report
  python main.py status         # Print current Tank state
"""
import sys
import os


def _check_keys():
    missing = []
    if not os.getenv("MONGODB_URI"):
        missing.append("MONGODB_URI (MongoDB Atlas connection string)")
    if not os.getenv("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY (needed for Apex Shark)")
    if not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY (needed for hunter/analyst sharks)")
    if not os.getenv("SERPER_API_KEY"):
        print("[warn] SERPER_API_KEY not set — web search disabled for sharks")
    if missing:
        print("[error] Missing required environment variables:")
        for m in missing:
            print(f"  export {m}")
        sys.exit(1)


def cmd_scan():
    from the_reef.scanner.monitor import run_scan, save_signals, DEFAULT_WATCHLIST
    print("[The Reef] Running scanner...")
    signals = run_scan(DEFAULT_WATCHLIST)
    save_signals(signals)
    if signals:
        print(f"\n🦈 {len(signals)} signal(s) detected:\n")
        for s in signals:
            print(f"  {s.signal_type:<20} {s.ticker:<6} @ ${s.price:.2f}  (value: {s.value:.2f})")
    else:
        print("No signals this cycle.")


def cmd_monitor():
    from the_reef.scanner.monitor import start_monitor, DEFAULT_WATCHLIST
    from the_reef.crew import run_deep_dive
    from the_reef.brokerage.the_tank import TheTank

    tank = TheTank()

    def on_signal(signals):
        top = signals[0]
        print(f"\n[apex] Activating deep-dive on {top.ticker} — {top.signal_type}")
        decision = run_deep_dive(top, tank)
        print(f"\n[apex] Decision recorded:\n{decision[:500]}")

    start_monitor(DEFAULT_WATCHLIST, on_signal=on_signal, interval_secs=300)


def cmd_dive(ticker: str):
    from the_reef.scanner.monitor import ScanSignal
    from the_reef.tools.market_data import get_price, get_volume_ratio
    from the_reef.crew import run_deep_dive
    from the_reef.brokerage.the_tank import TheTank
    from datetime import datetime, timezone

    price = get_price(ticker)
    if price is None:
        print(f"[error] Could not fetch price for {ticker}")
        sys.exit(1)

    vol = get_volume_ratio(ticker) or 1.0
    signal = ScanSignal(
        ticker=ticker.upper(),
        signal_type="MANUAL",
        priority=10,
        value=vol,
        price=price,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    print(f"\n[The Reef] Manual deep-dive on {ticker} @ ${price:.2f}\n")
    tank = TheTank()
    decision = run_deep_dive(signal, tank)
    print(f"\n{'='*60}\nAPEX SHARK DECISION\n{'='*60}\n{decision}")


def cmd_stops():
    from the_reef.crew import run_stop_loss_check
    from the_reef.brokerage.the_tank import TheTank
    print(run_stop_loss_check(TheTank()))


def cmd_dashboard():
    from the_reef.brokerage.the_tank import TheTank
    from the_reef.dashboard import run_live_dashboard
    run_live_dashboard(TheTank())


def cmd_report():
    from the_reef.brokerage.the_tank import TheTank
    from the_reef.brokerage.performance import format_report
    print(format_report(TheTank()))


def cmd_status():
    from the_reef.brokerage.the_tank import TheTank
    print(TheTank().summary())


COMMANDS = {
    "scan": cmd_scan,
    "monitor": cmd_monitor,
    "stops": cmd_stops,
    "dashboard": cmd_dashboard,
    "report": cmd_report,
    "status": cmd_status,
}


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0].lower()

    if cmd == "dive":
        if len(args) < 2:
            print("Usage: python main.py dive TICKER")
            sys.exit(1)
        _check_keys()
        cmd_dive(args[1].upper())
    elif cmd in COMMANDS:
        if cmd not in ("status", "report", "dashboard"):
            _check_keys()
        COMMANDS[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
