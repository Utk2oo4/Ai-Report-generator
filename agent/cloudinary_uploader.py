"""
Cloudinary Uploader — Uploads the generated .docx report to Cloudinary
and returns a publicly accessible secure URL.

Free tier: 25 GB storage / 25 GB bandwidth per month — plenty for daily reports.
"""

import os
import logging
from datetime import datetime

import cloudinary
import cloudinary.uploader

logger = logging.getLogger(__name__)


def _configure_cloudinary() -> None:
    """Configure Cloudinary credentials from environment variables."""
    cloudinary.config(
        cloud_name  = os.getenv("CLOUDINARY_CLOUD_NAME", ""),
        api_key     = os.getenv("CLOUDINARY_API_KEY", ""),
        api_secret  = os.getenv("CLOUDINARY_API_SECRET", ""),
        secure      = True,
    )


def upload_report(file_path: str) -> str:
    """
    Upload a .docx report file to Cloudinary.

    Args:
        file_path: Absolute path to the .docx file.

    Returns:
        A publicly accessible HTTPS URL for the uploaded file.

    Raises:
        ValueError: If Cloudinary credentials are missing.
        Exception:  If the upload fails.
    """
    _configure_cloudinary()

    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    if not cloud_name:
        raise ValueError(
            "Cloudinary credentials not configured. "
            "Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET."
        )

    # Build a unique public_id so each day's report is stored separately
    report_date  = datetime.now().strftime("%Y-%m-%d")
    public_id    = f"financial_reports/Daily_Financial_Report_{report_date}"
    display_name = f"Daily_Financial_Report_{report_date}.docx"

    logger.info("Uploading report to Cloudinary (public_id: %s)…", public_id)

    result = cloudinary.uploader.upload(
        file_path,
        public_id     = public_id,
        resource_type = "raw",        # required for non-image files
        overwrite     = True,         # replace same-day report if re-run
        tags          = ["financial_report", "daily", report_date],
        context       = {
            "report_date": report_date,
            "generated_by": "LangChain-Gemini-Agent",
        },
    )

    secure_url = result.get("secure_url", "")
    logger.info("Upload successful ✅  URL: %s", secure_url)

    # Append .docx so browsers/WhatsApp recognise the file type
    if not secure_url.endswith(".docx"):
        secure_url = secure_url + "?dl=" + display_name

    return secure_url
