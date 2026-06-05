"""
Market Tools — Fetches live Sensex and Nifty50 data via yfinance.
Tickers:
  - ^BSESN  → BSE Sensex
  - ^NSEI   → NSE Nifty 50
"""

import logging
from datetime import datetime
import yfinance as yf
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _fetch_index(ticker_symbol: str, display_name: str) -> dict:
    """Generic helper to fetch an index's latest price and daily change."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        # Fetch 5 days of data to ensure we always have at least 2 trading days
        hist = ticker.history(period="5d", interval="1d")

        if hist.empty:
            return {"error": f"No data returned for {display_name}", "name": display_name}

        current_price = float(hist["Close"].iloc[-1])

        if len(hist) >= 2:
            prev_price = float(hist["Close"].iloc[-2])
            change = current_price - prev_price
            pct_change = (change / prev_price) * 100
        else:
            prev_price = current_price
            change = 0.0
            pct_change = 0.0

        return {
            "name": display_name,
            "ticker": ticker_symbol,
            "current_price": round(current_price, 2),
            "previous_close": round(prev_price, 2),
            "change": round(change, 2),
            "percent_change": round(pct_change, 2),
            "direction": "↑" if change >= 0 else "↓",
            "trend": "Bullish" if change >= 0 else "Bearish",
            "as_of": datetime.now().strftime("%d %b %Y %I:%M %p IST"),
        }

    except Exception as exc:
        logger.error("Error fetching %s: %s", display_name, exc)
        return {"error": str(exc), "name": display_name}


@tool
def get_sensex_data() -> dict:
    """
    Fetch the current BSE Sensex index price, daily change, and percentage change.
    Returns a dict with: name, current_price, previous_close, change, percent_change,
    direction, trend, as_of.
    """
    return _fetch_index("^BSESN", "BSE Sensex")


@tool
def get_nifty50_data() -> dict:
    """
    Fetch the current NSE Nifty 50 index price, daily change, and percentage change.
    Returns a dict with: name, current_price, previous_close, change, percent_change,
    direction, trend, as_of.
    """
    return _fetch_index("^NSEI", "Nifty 50")
