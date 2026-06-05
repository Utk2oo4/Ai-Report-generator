"""
News Tools — Fetches top Indian business news headlines via NewsAPI.
Free tier: 100 requests/day — more than enough for one daily report.
"""

import os
import logging
from datetime import date
from newsapi import NewsApiClient
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def get_business_news() -> list:
    """
    Fetch the top 5 Indian business news headlines for today using NewsAPI.
    Returns a list of dicts, each containing: title, description, source, url, published_at.
    Falls back to a minimal error entry if the API call fails.
    """
    try:
        api_key = os.getenv("NEWSAPI_KEY", "")
        if not api_key:
            return [{"error": "NEWSAPI_KEY environment variable not set"}]

        api = NewsApiClient(api_key=api_key)

        response = api.get_top_headlines(
            category="business",
            country="in",
            page_size=5,
            language="en",
        )

        articles = response.get("articles", [])
        if not articles:
            # Fallback: general India news query if no headlines in business category
            response = api.get_everything(
                q="India business economy market",
                language="en",
                sort_by="publishedAt",
                page_size=5,
            )
            articles = response.get("articles", [])

        news_list = []
        for article in articles[:5]:
            news_list.append(
                {
                    "title": article.get("title") or "No title",
                    "description": article.get("description") or "",
                    "source": article.get("source", {}).get("name") or "Unknown",
                    "url": article.get("url") or "",
                    "published_at": (article.get("publishedAt") or "")[:10],
                }
            )

        logger.info("Fetched %d business news articles", len(news_list))
        return news_list

    except Exception as exc:
        logger.error("Error fetching business news: %s", exc)
        return [{"error": str(exc)}]
