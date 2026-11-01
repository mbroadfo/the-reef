"""The fixed research universe for historical replay, with static sectors.

NOT point-in-time and NOT survivorship-free. These are large, liquid U.S. names chosen by a
rule (broad large-cap coverage across sectors, a few laggards kept in on purpose) but chosen
today, so every one of them survived to be listed. Names that were delisted, acquired or
removed from the large-cap set during the sample (Yahoo carries almost none of them) are
absent, which flatters any long strategy. Sectors are today's classification applied to the
whole history. Every report built on this list must say so.
"""
from __future__ import annotations

SECTORS: dict[str, tuple[str, ...]] = {
    "Technology": ("AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CSCO", "IBM", "INTC", "QCOM", "TXN", "AMD", "ADBE", "CRM", "AMAT"),
    "Communication": ("GOOGL", "META", "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS"),
    "Consumer Discretionary": ("AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "TGT", "F", "GM", "BKNG"),
    "Consumer Staples": ("PG", "KO", "PEP", "WMT", "COST", "PM", "MO", "MDLZ", "CL", "KHC"),
    "Health Care": ("JNJ", "UNH", "LLY", "PFE", "MRK", "ABBV", "ABT", "TMO", "AMGN", "GILD", "BMY", "MDT", "CVS"),
    "Financials": ("JPM", "BAC", "WFC", "C", "GS", "MS", "AXP", "BLK", "SCHW", "USB", "V", "MA", "PYPL", "MET"),
    "Industrials": ("GE", "CAT", "BA", "HON", "UPS", "RTX", "LMT", "DE", "MMM", "UNP", "FDX"),
    "Energy": ("XOM", "CVX", "COP", "SLB", "OXY"),
    "Utilities": ("NEE", "DUK", "SO"),
    "Materials": ("LIN", "FCX", "NEM"),
    "Real Estate": ("AMT", "SPG", "PLD"),
}
BENCHMARK = "SPY"
SECTOR_OF = {sym: sector for sector, syms in SECTORS.items() for sym in syms}
UNIVERSE = tuple(sorted(SECTOR_OF))
