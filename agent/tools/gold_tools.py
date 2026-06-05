"""
Gold Tools — Fetches MCX Gold national rate via yfinance.

Method:
  - GC=F  → COMEX Gold Futures in USD per troy oz
  - USDINR=X → USD/INR exchange rate (live)
  - 1 troy oz = 31.1035 grams
  - MCX Gold is quoted in INR per 10 grams (standard lot unit)
  - Price per 10g = (GC=F_USD × USDINR) / 31.1035 × 10
"""

import logging
from datetime import datetime
import yfinance as yf
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

TROY_OZ_TO_GRAMS = 31.1035


@tool
def get_mcx_gold_price() -> dict:
    """
    Fetch the current MCX Gold national rate in India (INR per gram and per 10 grams).
    Uses COMEX Gold Futures (GC=F) converted to INR using the live USD/INR rate.
    Returns a dict with: price_per_gram_inr, price_per_10g_inr, change_per_10g,
    percent_change, direction, usd_price, usd_inr_rate, as_of.
    """
    try:
        # --- Fetch Gold price in USD ---
        gold_ticker = yf.Ticker("GC=F")
        gold_hist = gold_ticker.history(period="5d", interval="1d")

        if gold_hist.empty:
            return {"error": "Could not fetch gold futures data", "name": "MCX Gold"}

        gold_usd_current = float(gold_hist["Close"].iloc[-1])
        gold_usd_prev = (
            float(gold_hist["Close"].iloc[-2]) if len(gold_hist) >= 2 else gold_usd_current
        )

        # --- Fetch USD/INR rate ---
        usdinr_ticker = yf.Ticker("USDINR=X")
        usdinr_hist = usdinr_ticker.history(period="2d", interval="1d")

        if usdinr_hist.empty:
            # Fallback to a conservative rate if API fails
            inr_rate = 84.0
            logger.warning("USD/INR fetch failed. Using fallback rate: %s", inr_rate)
        else:
            inr_rate = float(usdinr_hist["Close"].iloc[-1])

        # --- Calculate INR prices per 10 grams ---
        price_per_10g_current = (gold_usd_current * inr_rate / TROY_OZ_TO_GRAMS) * 10
        price_per_10g_prev = (gold_usd_prev * inr_rate / TROY_OZ_TO_GRAMS) * 10

        change_10g = price_per_10g_current - price_per_10g_prev
        pct_change = (change_10g / price_per_10g_prev) * 100 if price_per_10g_prev else 0.0

        return {
            "name": "MCX Gold (24K – National Rate)",
            "price_per_gram_inr": round(price_per_10g_current / 10, 2),
            "price_per_10g_inr": round(price_per_10g_current, 2),
            "price_per_gram_inr_22k": round((price_per_10g_current / 10) * (22 / 24), 2),
            "change_per_10g": round(change_10g, 2),
            "percent_change": round(pct_change, 2),
            "direction": "↑" if change_10g >= 0 else "↓",
            "trend": "Rising" if change_10g >= 0 else "Falling",
            "usd_price_per_oz": round(gold_usd_current, 2),
            "usd_inr_rate": round(inr_rate, 2),
            "as_of": datetime.now().strftime("%d %b %Y %I:%M %p IST"),
        }

    except Exception as exc:
        logger.error("Error fetching MCX Gold price: %s", exc)
        return {"error": str(exc), "name": "MCX Gold"}
