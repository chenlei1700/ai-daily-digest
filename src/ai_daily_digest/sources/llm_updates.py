"""Large-model specific updates — distinguished from generic AI news.

We focus on: new model releases, benchmark results, pricing/API changes.
Sources:
  1. Simon Willison's blog (daily LLM engineering practice, high signal)
  2. HN with strict model-name keywords (filters out generic "AI" hype)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

import feedparser
import httpx

from ..models import Item

log = logging.getLogger(__name__)

SIMON_WILLISON_RSS = "https://simonwillison.net/atom/everything/"
HN_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"

# Official AI lab blogs — first-party announcements (releases, research, API changes)
OFFICIAL_BLOGS = {
    "OpenAI": "https://openai.com/blog/rss.xml",
    "Google DeepMind": "https://deepmind.google/blog/rss/",
    # Anthropic/Meta don't provide RSS as of 2026-06; fallback to HN coverage
}

# Model-specific keywords: filters out generic "AI" articles
MODEL_KEYWORDS = [
    # Major model families
    "Claude 4", "Claude 5", "GPT-5", "GPT-6", "o1", "o3",
    "Gemini 2", "Gemini 3", "Llama 4", "Llama 5",
    "DeepSeek", "Qwen", "Mistral", "Grok",
    # Chinese models
    "Kimi", "Doubao", "豆包", "ChatGLM", "智谱",
    "通义千问", "文心一言", "ERNIE",
    # Benchmarks & evaluations
    "benchmark", "MMLU", "HumanEval", "SWE-bench", "Chatbot Arena",
    # Model capabilities
    "reasoning model", "context window", "multimodal model",
    "weights released", "API pricing",
]


def fetch(limit: int = 30) -> list[Item]:
    items = list(_from_simon_willison(limit))
    items.extend(_from_official_blogs(limit))
    items.extend(_from_hn(limit))
    # de-dup by URL within batch
    seen, unique = set(), []
    for it in items:
        if it.url in seen:
            continue
        seen.add(it.url)
        unique.append(it)
    return unique[:limit]


def _from_hn(limit: int) -> list[Item]:
    cutoff = int(time.time()) - 72 * 3600
    out: list[Item] = []
    with httpx.Client(timeout=15.0) as client:
        for kw in MODEL_KEYWORDS:
            try:
                r = client.get(
                    HN_SEARCH,
                    params={
                        "query": kw,
                        "tags": "story",
                        "numericFilters": f"created_at_i>{cutoff},points>=15",
                        "hitsPerPage": 10,
                    },
                )
                r.raise_for_status()
                for h in r.json().get("hits", []):
                    url = h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"
                    out.append(
                        Item(
                            category="llm_updates",
                            title=h["title"],
                            url=url,
                            source="Hacker News",
                            published_at=datetime.fromtimestamp(h["created_at_i"]),
                            raw_metrics={
                                "points": h.get("points", 0),
                                "matched_keyword": kw,
                            },
                        )
                    )
            except Exception as e:
                log.warning("llm_updates HN fail %s: %s", kw, e)
    return out


def _from_simon_willison(limit: int) -> list[Item]:
    """Simon Willison writes daily about LLM engineering, tools, and research.

    High signal-to-noise (almost every post is LLM-relevant), so we trust his
    posts more than random HN hits — give them a fixed baseline in raw_metrics.
    """
    cutoff = int(time.time()) - 7 * 86400  # last 7 days
    try:
        feed = feedparser.parse(SIMON_WILLISON_RSS)
        out: list[Item] = []
        for e in feed.entries[:limit]:
            try:
                pub = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
                if pub and time.mktime(pub) < cutoff:
                    continue
                out.append(
                    Item(
                        category="llm_updates",
                        title=e.title,
                        url=e.link,
                        source="Simon Willison",
                        published_at=datetime(*pub[:6]) if pub else None,
                        summary=getattr(e, "summary", "")[:1000],
                        raw_metrics={"points": 120},  # trust score equivalent to HN ~120pt post
                    )
                )
            except Exception as ex:
                log.warning("simon willison parse fail: %s", ex)
        return out
    except Exception as e:
        log.warning("simon willison RSS fetch failed: %s", e)
        return []


def _from_official_blogs(limit: int) -> list[Item]:
    """Official AI lab blogs — announcements, releases, research updates.

    These are first-party sources with high trust (no speculation/rumors).
    Give them a baseline score of 80 (lower than Simon since less frequent but
    still higher than generic HN 15pt threshold).
    """
    cutoff = int(time.time()) - 7 * 86400  # last 7 days
    out: list[Item] = []
    for name, url in OFFICIAL_BLOGS.items():
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:10]:
                try:
                    pub = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
                    if pub and time.mktime(pub) < cutoff:
                        continue
                    out.append(
                        Item(
                            category="llm_updates",
                            title=e.title,
                            url=e.link,
                            source=name,
                            published_at=datetime(*pub[:6]) if pub else None,
                            summary=getattr(e, "summary", "")[:1000],
                            raw_metrics={"points": 80},  # official blog trust score
                        )
                    )
                except Exception as ex:
                    log.warning("%s parse fail: %s", name, ex)
        except Exception as e:
            log.warning("%s RSS fetch failed: %s", name, e)
    return out
