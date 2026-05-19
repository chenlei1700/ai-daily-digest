"""AI industry news — Hacker News (Algolia search) filtered for AI relevance.

We query HN with AI keywords and last 48h time window, then filter by points >= 30
so we get signals not noise. The dedup layer handles cross-day overlap.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

import httpx

from ..models import Item

log = logging.getLogger(__name__)

# HN Algolia search — free, no auth, well-documented
HN_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"
KEYWORDS = ["AI", "LLM", "GPT", "Claude", "Anthropic", "OpenAI", "Gemini", "agent"]


def fetch(limit: int = 30) -> list[Item]:
    cutoff = int(time.time()) - 48 * 3600  # last 48h
    items: list[Item] = []
    with httpx.Client(timeout=15.0) as client:
        for kw in KEYWORDS:
            try:
                r = client.get(
                    HN_SEARCH,
                    params={
                        "query": kw,
                        "tags": "story",
                        "numericFilters": f"created_at_i>{cutoff},points>=30",
                        "hitsPerPage": 20,
                    },
                )
                r.raise_for_status()
                for h in r.json().get("hits", []):
                    url = h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"
                    items.append(
                        Item(
                            category="ai_news",
                            title=h["title"],
                            url=url,
                            source="Hacker News",
                            published_at=datetime.fromtimestamp(h["created_at_i"]),
                            author=h.get("author"),
                            raw_metrics={
                                "points": h.get("points", 0),
                                "num_comments": h.get("num_comments", 0),
                                "hn_id": h["objectID"],
                            },
                        )
                    )
            except Exception as e:
                log.warning("HN search failed for %s: %s", kw, e)
    # dedup by URL within this batch (same story may match multiple keywords)
    seen, unique = set(), []
    for it in items:
        if it.url in seen:
            continue
        seen.add(it.url)
        unique.append(it)
    unique.sort(key=lambda i: i.raw_metrics.get("points", 0), reverse=True)
    return unique[:limit]
