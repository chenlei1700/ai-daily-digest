"""China politics / economy / industry — Chinese-language RSS aggregation.

Sources actually fresh & working (tested 2026-06-04):
  - BBC 中文 (simp) — 国际视角下的中国与重大事件中文报道
  - DW 中文 (德国之声) — 欧洲视角，深度分析
  - 36kr — 国内科技 / 产业 / 创业新闻 (实时性强)

User originally requested 财新 / 财联社 / 21 世纪经济报道, but all three
shut down their public RSS feeds and the RSSHub mirrors are blocked. Tested
新华网 + Sina RSS — they returned stale 2022-era content and were unusable.
"""
from __future__ import annotations

import logging
from datetime import datetime

import feedparser
import httpx

from ..models import Item

log = logging.getLogger(__name__)

FEEDS = [
    ("BBC 中文", "https://www.bbc.com/zhongwen/simp/index.xml"),
    ("DW 中文", "https://rss.dw.com/rdf/rss-chi-all"),
    ("36kr", "https://www.36kr.com/feed"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36",
    "Accept": "application/rss+xml,application/xml,text/xml,*/*",
}


def fetch(limit: int = 30) -> list[Item]:
    items: list[Item] = []
    per_feed = max(5, limit // len(FEEDS) + 1)
    with httpx.Client(timeout=15.0, headers=HEADERS, follow_redirects=True) as client:
        for source_name, url in FEEDS:
            try:
                r = client.get(url)
                r.raise_for_status()
                # Xinhua serves XML as text/xml with GBK or UTF-8; let
                # feedparser handle encoding from content bytes, not r.text.
                parsed = feedparser.parse(r.content)
                for entry in parsed.entries[:per_feed]:
                    title = (entry.get("title") or "").strip()
                    link = entry.get("link") or ""
                    if not (title and link):
                        continue
                    items.append(Item(
                        category="china_news",
                        title=title,
                        url=link,
                        source=source_name,
                        published_at=_parse_time(entry.get("published_parsed")
                                                or entry.get("updated_parsed")),
                        author=entry.get("author"),
                        summary=(entry.get("summary") or entry.get("description") or "")[:1500],
                    ))
            except Exception as e:
                log.warning("china_news: %s fetch failed: %s", source_name, e)
    # de-dup within batch by URL
    seen, unique = set(), []
    for it in items:
        if it.url in seen:
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
