"""Market data tools — yfinance wrapper + CrewAI tool definitions."""
from __future__ import annotations

import yfinance as yf
import pandas as pd
from typing import Optional
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# ── raw data helpers (used by scanner — no LLM) ──────────────────────────────

def get_price(ticker: str) -> Optional[float]:
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        return round(float(info.last_price), 2)
    except Exception:
        return None


def get_history(ticker: str, period: str = "3mo") -> Optional[pd.DataFrame]:
    try:
        return yf.Ticker(ticker).history(period=period)
    except Exception:
        return None


def get_volume_ratio(ticker: str) -> Optional[float]:
    """Current volume vs 20-day average volume."""
    hist = get_history(ticker, "1mo")
    if hist is None or len(hist) < 5:
        return None
    avg_vol = hist["Volume"].iloc[:-1].mean()
    current_vol = hist["Volume"].iloc[-1]
    if avg_vol == 0:
        return None
    return round(float(current_vol / avg_vol), 2)


def get_rsi(ticker: str, period: int = 14) -> Optional[float]:
    hist = get_history(ticker, "3mo")
    if hist is None or len(hist) < period + 1:
        return None
    delta = hist["Close"].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 1)


def get_price_change_pct(ticker: str, days: int = 1) -> Optional[float]:
    hist = get_history(ticker, "5d")
    if hist is None or len(hist) < 2:
        return None
    close = hist["Close"]
    return round(float((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100), 2)


def days_to_earnings(ticker: str) -> Optional[int]:
    try:
        t = yf.Ticker(ticker)
        calendar = t.calendar
        if calendar is None or calendar.empty:
            return None
        earnings_dates = calendar.columns.tolist()
        if not earnings_dates:
            return None
        next_earnings = pd.Timestamp(earnings_dates[0])
        delta = (next_earnings - pd.Timestamp.now()).days
        return max(0, int(delta))
    except Exception:
        return None


def get_52w_range(ticker: str) -> Optional[dict]:
    try:
        info = yf.Ticker(ticker).info
        return {
            "low": info.get("fiftyTwoWeekLow"),
            "high": info.get("fiftyTwoWeekHigh"),
            "current": get_price(ticker),
        }
    except Exception:
        return None


# ── CrewAI tools (used by shark agents) ──────────────────────────────────────

class MarketDataInput(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol e.g. NVDA")


class GetPriceTool(BaseTool):
    name: str = "Get Stock Price"
    description: str = "Get the current price and basic stats for a stock ticker"
    args_schema: type[BaseModel] = MarketDataInput

    def _run(self, ticker: str) -> str:
        price = get_price(ticker)
        rsi = get_rsi(ticker)
        change = get_price_change_pct(ticker)
        vol_ratio = get_volume_ratio(ticker)
        r52 = get_52w_range(ticker)

        if price is None:
            return f"Could not retrieve data for {ticker}"

        parts = [f"{ticker}: ${price:.2f}"]
        if change is not None:
            parts.append(f"1d change: {change:+.2f}%")
        if rsi is not None:
            parts.append(f"RSI: {rsi:.0f}")
        if vol_ratio is not None:
            parts.append(f"Volume ratio: {vol_ratio:.1f}x avg")
        if r52:
            low, high, cur = r52.get("low"), r52.get("high"), r52.get("current")
            if low and high and cur:
                pct_from_high = (cur - high) / high * 100
                parts.append(f"52w range: ${low:.2f}–${high:.2f} ({pct_from_high:+.1f}% from high)")

        dte = days_to_earnings(ticker)
        if dte is not None and dte < 30:
            parts.append(f"Earnings in {dte} days")

        return " | ".join(parts)


class GetHistoryTool(BaseTool):
    name: str = "Get Price History"
    description: str = "Get recent price history and technical summary for a stock"
    args_schema: type[BaseModel] = MarketDataInput

    def _run(self, ticker: str) -> str:
        hist = get_history(ticker, "1mo")
        if hist is None or hist.empty:
            return f"No history available for {ticker}"

        closes = hist["Close"].round(2)
        high = closes.max()
        low = closes.min()
        current = closes.iloc[-1]
        month_change = (current - closes.iloc[0]) / closes.iloc[0] * 100

        vol_avg = hist["Volume"].mean()
        vol_recent = hist["Volume"].iloc[-5:].mean()
        vol_trend = "increasing" if vol_recent > vol_avg * 1.2 else "normal"

        return (
            f"{ticker} 1-month summary: "
            f"Range ${low:.2f}–${high:.2f} | "
            f"Month change: {month_change:+.1f}% | "
            f"Volume trend: {vol_trend} | "
            f"Last 5 closes: {', '.join(f'${c:.2f}' for c in closes.iloc[-5:])}"
        )
