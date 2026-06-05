"""
Main Agent — Orchestrates the daily financial report pipeline.

Architecture:
  ┌─ APScheduler (BackgroundScheduler, 9:00 AM IST daily)
  │    └─ run_daily_report()
  │         ├─ Collect data (market, gold, news tools)
  │         ├─ Generate AI commentary via Gemini
  │         ├─ Build .docx via report_generator
  │         ├─ Upload to Cloudinary
  │         └─ Send WhatsApp via Twilio
  │
  └─ Flask server (binds to $PORT)
       ├─ GET /health   → liveness probe (Railway / Render)
       ├─ GET /status   → last run status
       └─ GET /trigger  → manual one-off run (for testing)

Run locally:
  python -m agent.main_agent            # scheduler mode
  python -m agent.main_agent --test     # immediate one-shot run
"""

import os
import sys
import logging
import threading
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone

# ── Load environment variables first ─────────────────────────────────────────
load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Import agent modules ──────────────────────────────────────────────────────
from langchain_groq import ChatGroq

from agent.tools.market_tools      import get_sensex_data, get_nifty50_data
from agent.tools.gold_tools        import get_mcx_gold_price
from agent.tools.news_tools        import get_business_news
from agent.report_generator        import generate_report
from agent.cloudinary_uploader     import upload_report
from agent.whatsapp_sender         import send_whatsapp_message

# ── LLM (Groq — free tier, ultra-fast inference) ─────────────────────────────
# Initialized lazily inside _generate_ai_commentary() so the Flask app can
# start and serve /health even when GROQ_API_KEY is not yet configured.

# ── State tracking ────────────────────────────────────────────────────────────
_last_run_status: dict = {
    "last_run_at"  : None,
    "status"       : "never_run",
    "report_url"   : None,
    "error"        : None,
}

IST = timezone("Asia/Kolkata")


# ── Core pipeline ─────────────────────────────────────────────────────────────

def _generate_ai_commentary(sensex: dict, nifty: dict, gold: dict, news: list) -> str:
    """
    Ask Gemini to write a 3–4 sentence market commentary.
    Falls back to a data-driven template if the API quota is exceeded or unavailable.
    """
    headlines = [
        n.get("title", "") for n in news[:3]
        if isinstance(n, dict) and "error" not in n
    ]

    prompt = f"""You are a professional Indian financial market analyst.
Based on today's market data below, write a concise 3–4 sentence commentary
for retail investors. Mention key trends, and any notable news that could
impact markets. Use simple, clear language — no jargon.

Market Data (today):
- BSE Sensex : {sensex.get('current_price', 'N/A')} ({sensex.get('direction', '')} {sensex.get('percent_change', 0):.2f}%)
- Nifty 50   : {nifty.get('current_price', 'N/A')} ({nifty.get('direction', '')} {nifty.get('percent_change', 0):.2f}%)
- MCX Gold   : ₹{gold.get('price_per_10g_inr', 'N/A')} / 10g ({gold.get('direction', '')} {gold.get('percent_change', 0):.2f}%)
- USD/INR    : ₹{gold.get('usd_inr_rate', 'N/A')}

Top News Headlines:
{chr(10).join(f'• {h}' for h in headlines)}

Write the commentary now:"""

    # ── Try Groq (primary) ────────────────────────────────────────────────────
    try:
        groq_api_key = os.getenv("GROQ_API_KEY", "")
        if not groq_api_key:
            raise ValueError("GROQ_API_KEY is not set")
        llm = ChatGroq(
            model       = "llama-3.3-70b-versatile",
            api_key     = groq_api_key,
            temperature = 0.35,
        )
        response = llm.invoke(prompt)
        logger.info("AI commentary generated via Groq (llama-3.3-70b-versatile)")
        return response.content.strip()
    except Exception as exc:
        logger.warning("Groq LLM failed (%s). Using data-driven fallback.", type(exc).__name__)

    # ── Fallback: data-driven template (no LLM needed) ───────────────────────
    s_dir   = sensex.get("direction", "→")
    s_pct   = abs(sensex.get("percent_change", 0))
    n_pct   = abs(nifty.get("percent_change", 0))
    g_pct   = abs(gold.get("percent_change", 0))
    s_trend = sensex.get("trend", "Neutral")
    g_trend = gold.get("trend", "Stable")

    return (
        f"Indian equity markets are showing a {s_trend.lower()} trend today, with the BSE Sensex "
        f"moving {s_dir} {s_pct:.2f}% and the Nifty 50 moving {abs(nifty.get('percent_change', 0)):.2f}%. "
        f"MCX Gold is {g_trend.lower()} by {g_pct:.2f}%, currently at "
        f"₹{gold.get('price_per_10g_inr', 'N/A')} per 10 grams (USD/INR: ₹{gold.get('usd_inr_rate', 'N/A')}). "
        f"Investors should review today's business news and global cues before making decisions.\n\n"
        f"⚠️ Note: AI commentary unavailable — check GROQ_API_KEY at https://console.groq.com"
    )


def run_daily_report() -> None:
    """
    Full pipeline: collect data → AI commentary → .docx → Cloudinary → WhatsApp.
    Called by APScheduler at 9:00 AM IST every day, or via /trigger endpoint.
    """
    global _last_run_status
    now_str = datetime.now(IST).strftime("%d %B %Y %I:%M %p IST")
    logger.info("=" * 60)
    logger.info("🚀  Starting daily financial report — %s", now_str)
    logger.info("=" * 60)

    _last_run_status["last_run_at"] = now_str
    _last_run_status["status"]      = "running"
    _last_run_status["error"]       = None

    try:
        # Step 1 — Collect market & news data
        logger.info("Step 1/5 — Fetching market data…")
        sensex_data = get_sensex_data.invoke({})
        nifty_data  = get_nifty50_data.invoke({})
        gold_data   = get_mcx_gold_price.invoke({})
        news_data   = get_business_news.invoke({})

        logger.info(
            "  Sensex: ₹%s  |  Nifty: ₹%s  |  Gold/10g: ₹%s",
            sensex_data.get("current_price", "ERR"),
            nifty_data.get("current_price", "ERR"),
            gold_data.get("price_per_10g_inr", "ERR"),
        )
        logger.info("  Business news articles fetched: %d", len(news_data))

        # Step 2 — AI commentary
        logger.info("Step 2/5 — Generating AI commentary via Gemini…")
        ai_commentary = _generate_ai_commentary(sensex_data, nifty_data, gold_data, news_data)
        logger.info("  Commentary: %s…", ai_commentary[:100])

        # Step 3 — Build .docx
        logger.info("Step 3/5 — Building .docx report…")
        report_path = generate_report(sensex_data, nifty_data, gold_data, news_data, ai_commentary)
        logger.info("  Saved to: %s", report_path)

        # Step 4 — Upload to Cloudinary
        logger.info("Step 4/5 — Uploading to Cloudinary…")
        report_url = upload_report(report_path)
        logger.info("  Public URL: %s", report_url)

        # Step 5 — Send WhatsApp
        logger.info("Step 5/5 — Sending WhatsApp message via Twilio…")
        date_str = datetime.now(IST).strftime("%d %B %Y")
        msg_sid  = send_whatsapp_message(report_url, date_str)
        logger.info("  Message SID: %s", msg_sid)

        # Clean up temp file
        if os.path.exists(report_path):
            os.remove(report_path)

        _last_run_status["status"]     = "success"
        _last_run_status["report_url"] = report_url

        logger.info("=" * 60)
        logger.info("🎉  Daily report completed successfully!")
        logger.info("=" * 60)

    except Exception as exc:
        logger.exception("❌  Daily report failed: %s", exc)
        _last_run_status["status"] = "failed"
        _last_run_status["error"]  = str(exc)


# ── Flask app ─────────────────────────────────────────────────────────────────

app = Flask(__name__)


@app.route("/health")
def health():
    """Liveness probe for Railway / Render."""
    return jsonify({
        "status"  : "ok",
        "service" : "Daily Financial Report Agent",
        "schedule": "10:00 AM IST (Asia/Kolkata)",
    })


@app.route("/status")
def status():
    """Return the status of the last report run."""
    return jsonify(_last_run_status)


@app.route("/trigger")
def trigger():
    """
    Manually trigger a report run (useful for testing without waiting for 9 AM).
    The run happens in a background thread so the HTTP response returns immediately.
    """
    if _last_run_status.get("status") == "running":
        return jsonify({"message": "A run is already in progress."}), 409

    thread = threading.Thread(target=run_daily_report, daemon=True)
    thread.start()
    return jsonify({
        "message": "Report generation triggered. Check /status for progress.",
    })


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--test" in sys.argv:
        # ── One-shot test mode (no scheduler, no server) ──────────────────────
        logger.info("🧪  TEST MODE — running report immediately…")
        run_daily_report()

    else:
        # ── Production mode ───────────────────────────────────────────────────
        # 1. Start the APScheduler
        scheduler = BackgroundScheduler(timezone=IST)
        scheduler.add_job(
            run_daily_report,
            CronTrigger(hour=10, minute=0, timezone=IST),
            id            = "daily_financial_report",
            name          = "Daily Financial Report — 10:00 AM IST",
            replace_existing = True,
        )
        scheduler.start()

        next_run = scheduler.get_job("daily_financial_report").next_run_time
        logger.info("📅  Scheduler started. Next run: %s", next_run)

        # 2. Start Flask (binds to $PORT — required by Railway / Render)
        port = int(os.getenv("PORT", 8080))
        logger.info("🌐  Web server starting on port %d", port)
        logger.info("     /health  → liveness probe")
        logger.info("     /status  → last run status")
        logger.info("     /trigger → manual run")
        app.run(host="0.0.0.0", port=port, debug=False)
