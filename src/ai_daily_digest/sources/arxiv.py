"""Papers source — Hugging Face Daily Papers (community-curated), with arXiv API fallback.

Primary path: HF Daily Papers API exposes upvote-ranked papers (no auth). When HF
is unavailable, fall back to the raw arXiv Atom feed sorted by submittedDate. The
category remains "arxiv" downstream — only the discovery mechanism changes.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import feedparser
import httpx

from ..models import Item

log = logging.getLogger(__name__)

HF_DAILY_PAPERS = "https://huggingface.co/api/daily_papers"
ARXIV_QUERY = "http://export.arxiv.org/api/query"
ARXIV_CATEGORIES = ["cs.AI", "cs.CL", "cs.LG"]


def fetch(limit: int = 30) -> list[Item]:
    items = _fetch_from_hf(limit)
    if items:
        return items
    log.warning("HF Daily Papers returned nothing; falling back to arXiv API")
    return _fetch_from_arxiv(limit)


def _fetch_from_hf(limit: int) -> list[Item]:
    today = date.today()
    for d in (today, today - timedelta(days=1)):
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(
                    HF_DAILY_PAPERS,
                    params={"date": d.isoformat(), "limit": limit},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as ex:
            log.warning("HF Daily Papers fetch failed for %s: %s", d, ex)
            continue
        if not data:
            continue
        items: list[Item] = []
        for entry in data:
            try:
                items.append(_hf_entry_to_item(entry))
            except Exception as ex:
                log.warning("HF paper parse fail: %s", ex)
        if items:
            return items
    return []


def _hf_entry_to_item(entry: dict) -> Item:
    paper = entry.get("paper") or {}
    arxiv_id = paper["id"]
    authors = [a.get("name", "") for a in paper.get("authors", [])[:3] if a.get("name")]
    org = (paper.get("organization") or {}).get("fullname") if isinstance(paper.get("organization"), dict) else None
    return Item(
        category="arxiv",
        title=paper["title"].strip().replace("\n", " "),
        url=f"https://arxiv.org/abs/{arxiv_id}",
        source="HF Daily Papers",
        published_at=_parse_iso(paper.get("publishedAt")),
        author=", ".join(authors),
        summary=(paper.get("summary") or "")[:1000],
        raw_metrics={
            "arxiv_id": arxiv_id,
            "upvotes": int(paper.get("upvotes") or 0),
            "num_comments": int(entry.get("numComments") or 0),
            "org": org,
        },
    )


def _fetch_from_arxiv(limit: int) -> list[Item]:
    cat_query = "+OR+".join(f"cat:{c}" for c in ARXIV_CATEGORIES)
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
                    published_at=_parse_struct_time(getattr(e, "published_parsed", None)),
                    author=", ".join(a.name for a in getattr(e, "authors", [])[:3]),
                    summary=getattr(e, "summary", "")[:1000],
                    raw_metrics={"arxiv_id": e.id.split("/")[-1]},
                )
            )
        except Exception as ex:
            log.warning("arxiv parse fail: %s", ex)
    return items


def _parse_iso(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_struct_time(tm):
    if not tm:
        return None
    return datetime(*tm[:6])
