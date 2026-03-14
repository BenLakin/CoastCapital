"""
news_ingest.py — ESPN sports news ingestion with LLM summarisation.

Fetches headlines from the ESPN news APIs for each supported sport,
optionally summarises them via the configured LLM provider, and stores
everything in ``modeling_internal.fact_sports_news``.

Public entry point: ``ingest_news(sport, summarize)``
"""

import logging
from datetime import datetime

import requests

from database import get_connection
from ingestion.schema_sync import dynamic_upsert
from llm.client import LLMClient

logger = logging.getLogger(__name__)

SCHEMA = "modeling_internal"

# ---------------------------------------------------------------------------
# ESPN news endpoints per sport
# ---------------------------------------------------------------------------

ESPN_NEWS_URLS: dict[str, str] = {
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news",
    "ncaa_mbb": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/news",
    "mlb": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/news",
    "ncaa_fbs": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/news",
}

# Focus teams for the dashboard (team name → sport key)
FOCUS_TEAMS: dict[str, list[str]] = {
    "nfl": ["Indianapolis Colts", "Colts"],
    "mlb": ["Chicago Cubs", "Cubs"],
    "ncaa_fbs": ["Iowa Hawkeyes", "Iowa", "Hawkeyes"],
    "ncaa_mbb": ["Iowa Hawkeyes", "Iowa", "Hawkeyes"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _match_focus_team(text: str, sport: str) -> str | None:
    """Return the canonical focus-team name if *text* mentions one, else None."""
    lower = text.lower()
    aliases = FOCUS_TEAMS.get(sport, [])
    for alias in aliases:
        if alias.lower() in lower:
            # Return the first (canonical) alias
            return aliases[0]
    return None


def fetch_espn_news(sport: str, limit: int = 25) -> list[dict]:
    """Fetch news articles from the ESPN news API for *sport*.

    Returns
    -------
    list of dicts with keys: headline, description, article_url, published_at.
    """
    url = ESPN_NEWS_URLS.get(sport)
    if not url:
        logger.warning("fetch_espn_news: no URL configured for sport=%s", sport)
        return []

    try:
        resp = requests.get(url, params={"limit": limit}, timeout=30)
        resp.raise_for_status()
        articles_raw = resp.json().get("articles", [])
    except Exception as exc:
        logger.error("fetch_espn_news: failed for sport=%s — %s", sport, exc)
        return []

    articles: list[dict] = []
    for a in articles_raw:
        headline = a.get("headline", "")
        description = a.get("description", "")

        # Extract article URL
        article_url = ""
        links = a.get("links", {})
        if isinstance(links, dict):
            web = links.get("web", {})
            if isinstance(web, dict):
                article_url = web.get("href", "")
            elif isinstance(web, list) and web:
                article_url = web[0].get("href", "")
        if not article_url:
            article_url = a.get("link", "") or a.get("url", "")

        published = a.get("published", "")

        articles.append({
            "headline": headline,
            "description": description,
            "article_url": article_url,
            "published_at": published,
        })

    logger.info("fetch_espn_news: %d articles for sport=%s", len(articles), sport)
    return articles


# ---------------------------------------------------------------------------
# Main ingest
# ---------------------------------------------------------------------------

def ingest_news(sport: str = "all", summarize: bool = True) -> dict:
    """Fetch ESPN news, optionally summarise with LLM, and store.

    Parameters
    ----------
    sport     : ``"nfl"`` | ``"ncaa_mbb"`` | ``"mlb"`` | ``"ncaa_fbs"`` | ``"all"``
    summarize : If True, call the LLM to generate a summary for each article.

    Returns
    -------
    dict with per-sport counts of articles fetched, stored, and summarised.
    """
    sports = list(ESPN_NEWS_URLS.keys()) if sport == "all" else [sport]

    llm = LLMClient() if summarize else None
    conn = get_connection(SCHEMA)
    cursor = conn.cursor()

    results: dict[str, dict] = {}

    for sp in sports:
        articles = fetch_espn_news(sp)
        stored = 0
        summarised = 0

        for article in articles:
            headline = article["headline"]
            description = article["description"]
            article_url = article["article_url"]
            published_at = article["published_at"]

            if not headline:
                continue

            # Determine if this article relates to a focus team
            combined_text = f"{headline} {description}"
            focus_team = _match_focus_team(combined_text, sp)

            # LLM summarisation
            llm_summary = None
            llm_model = None
            if llm and description:
                context = ""
                if focus_team:
                    context = f"Pay special attention to {focus_team}."
                llm_summary = llm.summarize(description, context=context)
                llm_model = llm.model
                if llm_summary and not llm_summary.startswith("(LLM summary"):
                    summarised += 1

            try:
                dynamic_upsert(cursor, SCHEMA, "fact_sports_news", {
                    "sport": sp,
                    "headline": headline[:500],
                    "description": description,
                    "article_url": article_url[:1000] if article_url else None,
                    "source": "espn",
                    "published_at": published_at if published_at else None,
                    "llm_summary": llm_summary,
                    "llm_model": llm_model,
                    "focus_team": focus_team,
                    "fetched_at": datetime.now(),
                })
                stored += 1
            except Exception as exc:
                logger.warning(
                    "ingest_news: failed to store article '%s' — %s",
                    headline[:60], exc,
                )

        results[sp] = {
            "articles_fetched": len(articles),
            "articles_stored": stored,
            "summaries_generated": summarised,
        }
        logger.info(
            "ingest_news: sport=%s  fetched=%d  stored=%d  summarised=%d",
            sp, len(articles), stored, summarised,
        )

    conn.commit()
    cursor.close()
    conn.close()

    return {"status": "ok", "results": results}
