"""China politics / economy / industry — Chinese-language aggregation.

Sources:
  - 财联社 (Cailianshe) telegraph 7×24 — scraped from m.cls.cn/telegraph since
    public RSS no longer exists. Page embeds news data in `__NEXT_DATA__` JS.
    Updates throughout the day with real-time market/policy snippets.
  - DW 中文 — 欧洲视角，深度
  - 36kr — 国内科技 / 产业 / 创业新闻

Notes:
  - User originally requested 财新 / 21 世纪经济报道: both shut down public RSS.
  - 新华网 / Sina RSS returned 2022-era stale content and were dropped.
  - BBC 中文 worked but removed at user request.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime

import feedparser
import httpx

from ..models import Item

log = logging.getLogger(__name__)

FEEDS = [
    ("DW 中文", "https://rss.dw.com/rdf/rss-chi-all"),
    ("36kr", "https://www.36kr.com/feed"),
]

CLS_URL = "https://m.cls.cn/telegraph"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36",
    "Accept": "text/html,application/rss+xml,application/xml,*/*",
}


def fetch(limit: int = 30) -> list[Item]:
    items: list[Item] = []
    items.extend(_fetch_cls(limit_n=20))
    items.extend(_fetch_rss_feeds(per_feed=max(5, (limit - 20) // max(1, len(FEEDS)) + 1)))
    # de-dup by URL within batch
    seen, unique = set(), []
    for it in items:
        if not it.url or it.url in seen:
            continue
        seen.add(it.url)
        unique.append(it)
    return unique[:limit]


def _fetch_cls(limit_n: int) -> list[Item]:
    """Scrape 财联社 telegraph mobile page; data is in __NEXT_DATA__ inline JS."""
    items: list[Item] = []
    try:
        with httpx.Client(timeout=15.0, headers=HEADERS, follow_redirects=True) as client:
            r = client.get(CLS_URL)
            r.raise_for_status()
        start = r.text.find("__NEXT_DATA__ = ")
        if start < 0:
            log.warning("china_news: CLS __NEXT_DATA__ marker not found")
            return []
        # raw_decode parses until end of first valid JSON object
        obj, _ = json.JSONDecoder().raw_decode(r.text[start + len("__NEXT_DATA__ = "):])
        roll = obj.get("props", {}).get("initialState", {}).get("roll_data", [])
        for entry in roll[:limit_n]:
            if not isinstance(entry, dict):
                continue
            title = (entry.get("title") or entry.get("brief") or "").strip()
            if not title:
                continue
            url = entry.get("shareurl") or f"https://www.cls.cn/detail/{entry.get('id')}"
            ctime = entry.get("ctime")
            try:
                published = datetime.fromtimestamp(int(ctime)) if ctime else None
            except Exception:
                published = None
            items.append(Item(
                category="china_news",
                title=title,
                url=url,
                source="财联社",
                published_at=published,
                summary=(entry.get("content") or entry.get("brief") or "")[:1500],
                raw_metrics={"cls_id": entry.get("id")},
            ))
        log.info("china_news: CLS scraped %d items", len(items))
    except Exception as e:
        log.warning("china_news: CLS scrape failed: %s", e)
    return items


def _fetch_rss_feeds(per_feed: int) -> list[Item]:
    items: list[Item] = []
    with httpx.Client(timeout=15.0, headers=HEADERS, follow_redirects=True) as client:
        for source_name, url in FEEDS:
            try:
                r = client.get(url)
                r.raise_for_status()
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
    return items


def _parse_time(tm):
    if not tm:
        return None
    try:
        return datetime(*tm[:6])
    except Exception:
        return None
