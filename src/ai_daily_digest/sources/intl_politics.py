"""International politics — RSS aggregation from authoritative wire services.

Sources:
  - BBC World News + BBC Politics
  - Al Jazeera English (full RSS)

User originally requested Reuters but Reuters retired its public RSS endpoint;
BBC fills the same neutral-wire role and stays accessible from mainland China.
"""
from __future__ import annotations

import logging
from datetime import datetime

import feedparser
import httpx

from ..models import Item

log = logging.getLogger(__name__)

FEEDS = [
    ("BBC World", "http://feeds.bbci.co.uk/news/world/rss.xml"),
    ("BBC Politics", "http://feeds.bbci.co.uk/news/politics/rss.xml"),
    ("Al Jazeera English", "https://www.aljazeera.com/xml/rss/all.xml"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36",
}


def fetch(limit: int = 30) -> list[Item]:
    items: list[Item] = []
    per_feed = max(5, limit // len(FEEDS) + 1)
    with httpx.Client(timeout=15.0, headers=HEADERS, follow_redirects=True) as client:
        for source_name, url in FEEDS:
            try:
                r = client.get(url)
                r.raise_for_status()
                parsed = feedparser.parse(r.text)
                for entry in parsed.entries[:per_feed]:
                    items.append(Item(
                        category="intl_politics",
                        title=entry.get("title", "").strip(),
                        url=entry.get("link", ""),
                        source=source_name,
                        published_at=_parse_time(entry.get("published_parsed")),
                        author=entry.get("author"),
                        summary=(entry.get("summary") or entry.get("description") or "")[:1500],
                    ))
            except Exception as e:
                log.warning("intl_politics: %s fetch failed: %s", source_name, e)
    # de-dup by URL within batch
    seen, unique = set(), []
    for it in items:
        if not it.url or it.url in seen:
            continue
        seen.add(it.url)
        unique.append(it)
    return unique[:limit]


def _parse_time(tm):
    if not tm:
        return None
    try:
        return datetime(*tm[:6])
    except Exception:
        return None
