"""Large-model specific updates — distinguished from generic AI news.

We focus on: new model releases, benchmark results, pricing/API changes.
Sources:
  1. Hugging Face Daily Papers (already curated for ML researchers)
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

HF_DAILY_RSS = "https://huggingface.co/papers"  # HF doesn't expose rss; we'll use HN+keywords primarily
HN_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"

# Model-specific keywords: filters out generic "AI" articles
MODEL_KEYWORDS = [
    "Claude 4", "Claude 5", "GPT-5", "GPT-6", "o1", "o3",
    "Gemini 2", "Gemini 3", "Llama 4", "Llama 5",
    "DeepSeek", "Qwen", "Mistral", "Grok",
    "benchmark", "MMLU", "HumanEval", "SWE-bench",
]


def fetch(limit: int = 30) -> list[Item]:
    items = list(_from_hn(limit))
    items.extend(_from_hf_papers(limit))
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


def _from_hf_papers(limit: int) -> list[Item]:
    # Hugging Face Daily Papers page has a feed at /papers via parsing; skip for now.
    # User can extend this later. Returning empty keeps the rest of the pipeline robust.
    return []
