"""
WhatsApp Sender — Sends the daily financial report URL via Twilio WhatsApp API.

Setup:
  1. Go to https://console.twilio.com → Messaging → Try it out → Send a WhatsApp message
  2. Connect your WhatsApp number to the Twilio sandbox by sending:
       "join <sandbox-word>"  to  +1 415 523 8886
  3. Fill in TWILIO_* env variables in .env
"""

import os
import logging
from datetime import datetime
from twilio.rest import Client

logger = logging.getLogger(__name__)


def send_whatsapp_message(report_url: str, report_date: str) -> str:
    """
    Send a WhatsApp message containing the Cloudinary report URL via Twilio.

    Args:
        report_url:  The public HTTPS URL of the uploaded .docx report.
        report_date: Human-readable date string, e.g. "04 June 2026".

    Returns:
        The Twilio message SID.

    Raises:
        ValueError: If required Twilio environment variables are missing.
        TwilioRestException: If the API call fails.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    to_number   = os.getenv("TWILIO_WHATSAPP_TO", "")

    if not account_sid or not auth_token:
        raise ValueError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set.")
    if not to_number:
        raise ValueError("TWILIO_WHATSAPP_TO must be set (e.g. whatsapp:+919876543210).")

    client = Client(account_sid, auth_token)

    # ── Compose message body ─────────────────────────────────────────────────
    body = (
        f"📊 *Daily Financial Report*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 *Date:* {report_date}\n"
        f"🕙 *Generated at:* 10:00 AM IST\n\n"
        f"Your daily market report is ready! 🎯\n\n"
        f"📎 *Download Report (.docx):*\n"
        f"{report_url}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 *Report includes:*\n"
        f"  • BSE Sensex — latest price & change\n"
        f"  • Nifty 50  — latest price & change\n"
        f"  • MCX Gold  — national rate (24K & 22K)\n"
        f"  • Top India business news headline\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"_⚠️ For informational purposes only. Not financial advice._"
    )

    logger.info("Sending WhatsApp message to %s…", to_number)
    message = client.messages.create(
        from_ = from_number,
        to    = to_number,
        body  = body,
    )

    logger.info("WhatsApp message sent ✅  SID: %s | Status: %s", message.sid, message.status)
    return message.sid
