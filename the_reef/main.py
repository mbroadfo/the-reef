#!/usr/bin/env python
"""The Reef — entry point.

Usage:
  python -m the_reef.main scan           # Run one scanner cycle and print signals
  python -m the_reef.main monitor        # Run scanner continuously (local mode)
  python -m the_reef.main dive NVDA      # Run full shark panel on a specific ticker
  python -m the_reef.main stops          # Check all open positions for stop-loss breaches
  python -m the_reef.main dashboard      # Launch live Rich terminal dashboard
  python -m the_reef.main report         # Print performance report
  python -m the_reef.main status         # Print current Tank state
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
        print(f"\n{len(signals)} signal(s) detected:\n")
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
    positions_before = set(tank.positions.keys())
    decision = run_deep_dive(signal, tank)
    print(f"\n{'='*60}\nAPEX SHARK DECISION\n{'='*60}\n{decision}")

    # Send SMS if Apex opened a new position
    new_tickers = set(tank.positions.keys()) - positions_before
    if new_tickers:
        from .notifications.sms import trade_alert
        for t in new_tickers:
            pos = tank.positions[t]
            trade_alert(
                ticker=t,
                shares=int(pos.shares),
                price=pos.entry_price,
                stop=pos.stop_loss or 0.0,
                target=pos.target_price or 0.0,
                conviction=pos.conviction,
                cash_remaining=tank.cash,
            )


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
    from the_reef.notifications.sms import daily_digest
    tank = TheTank()
    print(format_report(tank))
    daily_digest(
        portfolio_value=tank.portfolio_value(),
        pnl=tank.total_pnl(),
        pnl_pct=tank.total_pnl_pct(),
        positions=tank.positions,
        cash=tank.cash,
    )


def cmd_status():
    from the_reef.brokerage.the_tank import TheTank
    print(TheTank().summary())


def cmd_reset():
    from the_reef.brokerage.the_tank import get_db, STARTING_CASH
    db = get_db()
    positions_deleted = db.positions.delete_many({}).deleted_count
    trades_deleted = db.trades.delete_many({}).deleted_count
    signals_deleted = db.signals.delete_many({}).deleted_count
    db.portfolio.update_one({"_id": "main"}, {"$set": {"cash": STARTING_CASH, "starting_cash": STARTING_CASH, "next_trade_id": 1}})
    print(f"[reset] Portfolio reset to ${STARTING_CASH:,.0f} cash")
    print(f"[reset] Cleared {positions_deleted} position(s), {trades_deleted} trade(s), {signals_deleted} signal(s)")


COMMANDS = {
    "scan": cmd_scan,
    "monitor": cmd_monitor,
    "stops": cmd_stops,
    "dashboard": cmd_dashboard,
    "report": cmd_report,
    "status": cmd_status,
    "reset": cmd_reset,
}


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0].lower()

    if cmd == "dive":
        if len(args) < 2:
            print("Usage: python -m the_reef.main dive TICKER")
            sys.exit(1)
        _check_keys()
        cmd_dive(args[1].upper())
    elif cmd in COMMANDS:
        if cmd not in ("status", "report", "dashboard", "reset"):
            _check_keys()
        COMMANDS[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
