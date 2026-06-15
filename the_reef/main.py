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
  python -m the_reef.main sell TICKER    # Sell all shares of TICKER at market
  python -m the_reef.main sell TICKER N  # Sell N shares of TICKER at market
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
    from the_reef.scanner.monitor import ScanSignal, SIGNAL_TYPES
    from the_reef.tools.market_data import get_price, get_volume_ratio
    from the_reef.crew import run_deep_dive
    from the_reef.brokerage.the_tank import TheTank
    from datetime import datetime, timezone

    # Allow env var overrides — used by deep_dive.yml for private companies / specific signals
    signal_type   = os.getenv("SIGNAL_TYPE", "MANUAL")
    price_env     = os.getenv("PRICE_OVERRIDE")
    value_env     = os.getenv("SIGNAL_VALUE")

    if price_env:
        price = float(price_env)
    else:
        price = get_price(ticker)
        if price is None:
            print(f"[error] Could not fetch price for {ticker}")
            sys.exit(1)

    value = float(value_env) if value_env else (get_volume_ratio(ticker) or 1.0)
    priority = SIGNAL_TYPES.get(signal_type, 8)

    signal = ScanSignal(
        ticker=ticker.upper(),
        signal_type=signal_type,
        priority=priority,
        value=value,
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


def cmd_sell(ticker: str, shares_str: str | None = None):
    from the_reef.tools.market_data import get_price
    from the_reef.brokerage.the_tank import TheTank

    tank = TheTank()
    positions = tank.positions
    if ticker not in positions:
        print(f"[error] No open position in {ticker}")
        sys.exit(1)

    pos = positions[ticker]
    price = get_price(ticker)
    if price is None:
        print(f"[error] Could not fetch price for {ticker}")
        sys.exit(1)

    shares = float(shares_str) if shares_str else pos.shares
    pnl = (price - pos.entry_price) * shares

    ok, msg = tank.sell(ticker=ticker, shares=shares, price=price, reason="Manual exit via CLI")
    print(f"[The Reef] {msg}")

    if ok:
        from the_reef.notifications.sms import send_sms
        pnl_str = f"+${pnl:.0f}" if pnl >= 0 else f"-${abs(pnl):.0f}"
        send_sms(
            "REEF SELL",
            f"SOLD {int(shares)} {ticker} @ ${price:.2f}\n"
            f"Entry ${pos.entry_price:.2f} | P&L {pnl_str}\n"
            f"Cash: ${tank.cash:,.0f}",
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
    tank.take_snapshot("daily_report")
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
    from datetime import datetime, timezone
    db = get_db()
    positions_deleted = db.positions.delete_many({}).deleted_count
    trades_deleted = db.trades.delete_many({}).deleted_count
    signals_deleted = db.signals.delete_many({}).deleted_count
    snapshots_deleted = db.portfolio_snapshots.delete_many({}).deleted_count
    db.decisions.delete_many({})
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    db.portfolio.update_one({"_id": "main"}, {"$set": {"cash": STARTING_CASH, "starting_cash": STARTING_CASH, "next_trade_id": 1}})
    db.portfolio_snapshots.insert_one({
        "timestamp": now,
        "portfolio_value": STARTING_CASH,
        "cash": STARTING_CASH,
        "equity": 0.0,
        "event": "reset",
    })
    print(f"[reset] Portfolio reset to ${STARTING_CASH:,.0f} cash")
    print(f"[reset] Cleared {positions_deleted} position(s), {trades_deleted} trade(s), {signals_deleted} signal(s), {snapshots_deleted} snapshot(s)")


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
    elif cmd == "sell":
        if len(args) < 2:
            print("Usage: python -m the_reef.main sell TICKER [SHARES]")
            sys.exit(1)
        if not os.getenv("MONGODB_URI"):
            print("[error] MONGODB_URI environment variable not set")
            sys.exit(1)
        cmd_sell(args[1].upper(), args[2] if len(args) >= 3 else None)
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
