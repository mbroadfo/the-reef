"""Download free daily history for the research universe + SPY into the local cache (one-time).

Run:  uv run python tools/fetch_history.py [--start 2015-01-01]
Needs no account or key. Writes only to the cache directory outside the repository.
"""
from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal

from the_reef.backtest import cache
from the_reef.backtest.universe import BENCHMARK, UNIVERSE


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default=date.today().isoformat())
    args = ap.parse_args()
    import yfinance as yf  # noqa: PLC0415

    symbols = [*UNIVERSE, BENCHMARK]
    frame = yf.download(symbols, start=args.start, end=args.end, auto_adjust=False, actions=True,
                        group_by="ticker", progress=False, threads=True)
    for sym in symbols:
        df = frame[sym].dropna(subset=["Open", "High", "Low", "Close"])
        rows = [cache.RawRow(
            idx.date(), Decimal(str(r["Open"])), Decimal(str(r["High"])), Decimal(str(r["Low"])), Decimal(str(r["Close"])),
            Decimal(str(r["Adj Close"])), int(r["Volume"] or 0),
            Decimal(str(r.get("Dividends", 0) or 0)), Decimal(str(r.get("Stock Splits", 0) or 0)),
        ) for idx, r in df.iterrows()]
        cache.write(sym, rows)
        print(f"{sym:6} {len(rows):5} rows  {rows[0].day if rows else '-'} .. {rows[-1].day if rows else '-'}")


if __name__ == "__main__":
    main()
