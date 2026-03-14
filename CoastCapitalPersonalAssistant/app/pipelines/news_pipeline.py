"""
News Pipeline — RSS aggregator with Claude summaries.
Categories: world, technology, ai, b2b
"""
import logging
from datetime import datetime, timedelta

import anthropic
import feedparser

from app.config import Config
from app.db import get_conn, log_daily_activity

logger = logging.getLogger(__name__)

RSS_FEEDS = {
    "world": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    ],
    "technology": [
        "https://techcrunch.com/feed/",
        "https://www.wired.com/feed/rss",
    ],
    "ai": [
        "https://venturebeat.com/category/ai/feed/",
        "https://feeds.feedburner.com/oreilly/radar",
        "https://www.technologyreview.com/feed/",
    ],
    "b2b": [
        "https://www.businessinsider.com/rss",
        "https://hbr.org/resources/rss/topics/sales/feed",
        "https://feeds.feedburner.com/entrepreneur/latest",
    ],
}


class NewsPipeline:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    def fetch_and_summarize(self, categories: list[str] = None) -> dict:
        if categories is None:
            categories = ["world", "technology", "ai", "b2b"]

        all_articles = {}
        summaries = {}

        for cat in categories:
            articles = self._fetch_category(cat)
            all_articles[cat] = articles
            if articles:
                summaries[cat] = self._summarize_category(cat, articles)
                self._cache_news(cat, articles, summaries[cat])

        total_articles = sum(len(a) for a in all_articles.values())
        log_daily_activity("news-summary", news_articles=total_articles)
        return {
            "categories": list(categories),
            "summaries": summaries,
            "article_counts": {cat: len(arts) for cat, arts in all_articles.items()},
            "fetched_at": datetime.now().isoformat(),
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _fetch_category(self, category: str) -> list[dict]:
        return self._fetch_rss(category)[:15]

    def _fetch_rss(self, category: str) -> list[dict]:
        feeds = RSS_FEEDS.get(category, [])
        articles = []
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:8]:
                    articles.append({
                        "title": entry.get("title", ""),
                        "source": feed.feed.get("title", feed_url),
                        "url": entry.get("link", ""),
                        "description": entry.get("summary", "")[:400],
                        "content": "",
                    })
            except Exception as e:
                logger.warning("RSS parse error %s: %s", feed_url, e)
        return articles

    def _summarize_category(self, category: str, articles: list[dict]) -> str:
        headlines = "\n".join(
            f"- {a['title']} ({a['source']}): {a['description'][:150]}"
            for a in articles
        )
        focus_note = ""
        if category == "ai":
            focus_note = " Focus on practical AI applications and enterprise use cases."
        elif category == "b2b":
            focus_note = " Focus on business strategy, revenue growth, and sales insights."

        prompt = (
            f"Summarize these {category} news headlines into 3-4 key takeaways. "
            f"Be concise and actionable.{focus_note}\n\n{headlines}"
        )

        try:
            resp = self.client.messages.create(
                model=Config.CLAUDE_MODEL,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text
        except Exception as e:
            logger.warning("News summary failed for %s: %s", category, e)
            return "\n".join(a["title"] for a in articles[:5])

    def _cache_news(self, category: str, articles: list[dict], summary: str):
        try:
            conn = get_conn()
            cur = conn.cursor()
            # Delete old entries for this category (keep fresh)
            cur.execute("DELETE FROM news_cache WHERE category=%s AND fetched_at < NOW() - INTERVAL 1 DAY", (category,))
            for art in articles[:10]:
                cur.execute(
                    "INSERT INTO news_cache (category, title, source, url, summary) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (category, art["title"], art["source"], art["url"], summary),
                )
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning("News cache write failed: %s", e)
