"""arXiv source — recent CS.AI / CS.CL / CS.LG submissions.

arXiv exposes a public Atom API; no auth needed. We sort by submittedDate desc
and let the daily window be handled by the dedup layer (yesterday's papers will
already be in seen.db).
"""
from __future__ import annotations

import logging

import feedparser

from ..models import Item

log = logging.getLogger(__name__)

ARXIV_QUERY = "http://export.arxiv.org/api/query"
CATEGORIES = ["cs.AI", "cs.CL", "cs.LG"]


def fetch(limit: int = 30) -> list[Item]:
    cat_query = "+OR+".join(f"cat:{c}" for c in CATEGORIES)
    url = (
        f"{ARXIV_QUERY}?search_query={cat_query}"
        f"&sortBy=submittedDate&sortOrder=descending&max_results={limit}"
    )
    feed = feedparser.parse(url)
    items: list[Item] = []
    for e in feed.entries:
        try:
            items.append(
                Item(
                    category="arxiv",
                    title=e.title.strip().replace("\n", " "),
                    url=e.link,
                    source="arXiv",
                    published_at=_parse_date(getattr(e, "published_parsed", None)),
                    author=", ".join(a.name for a in getattr(e, "authors", [])[:3]),
                    summary=getattr(e, "summary", "")[:1000],
                    raw_metrics={"arxiv_id": e.id.split("/")[-1]},
                )
            )
        except Exception as ex:
            log.warning("arxiv parse fail: %s", ex)
    return items


def _parse_date(tm):
    if not tm:
        return None
    from datetime import datetime
    return datetime(*tm[:6])
