"""GitHub Trending — scrapes the public /trending HTML page.

The Search API can't tell us *trending* (it only sorts by cumulative stars),
so we parse the official trending page. We default to `since=weekly` because:
  - daily is too noisy and often dominated by random non-AI repos
  - monthly is too slow to surface new projects
  - weekly is the sweet spot for a daily digest reader

We filter to AI-relevant rows after scraping (no official topic filter on
the trending page — we approximate via keyword match against title +
description + language).
"""
from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

from ..models import Item

log = logging.getLogger(__name__)

TRENDING_URL = "https://github.com/trending"
AI_KEYWORDS = (
    "ai", "agent", "llm", "gpt", "claude", "gemini", "rag", "embedding",
    "transformer", "diffusion", "deep learning", "machine learning",
    "neural", "ml", "openai", "anthropic", "huggingface",
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (ai-daily-digest)",
    "Accept": "text/html,application/xhtml+xml",
}


def fetch(limit: int = 30, since: str = "weekly") -> list[Item]:
    items: list[Item] = []
    try:
        with httpx.Client(timeout=20.0, headers=HEADERS, follow_redirects=True) as client:
            r = client.get(TRENDING_URL, params={"since": since})
            r.raise_for_status()
    except Exception as e:
        log.warning("github trending fetch failed: %s", e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    for row in soup.select("article.Box-row"):
        try:
            a = row.select_one("h2 a")
            if not a or not a.get("href"):
                continue
            full_name = a["href"].lstrip("/").strip()
            url = "https://github.com/" + full_name

            desc_el = row.select_one("p")
            description = desc_el.get_text(" ", strip=True) if desc_el else ""

            lang_el = row.select_one('[itemprop="programmingLanguage"]')
            language = lang_el.get_text(strip=True) if lang_el else None

            total_stars = _parse_count(row.select_one('a[href$="/stargazers"]'))
            forks = _parse_count(row.select_one('a[href$="/forks"]'))
            new_stars = _parse_new_stars(row)

            it = Item(
                category="github_trending",
                title=f"{full_name} — {description}" if description else full_name,
                url=url,
                source="GitHub Trending",
                author=full_name.split("/")[0],
                raw_metrics={
                    "stars": total_stars,
                    "forks": forks,
                    "new_stars": new_stars,
                    "trending_period": since,
                    "language": language,
                },
            )

            if _is_ai_relevant(full_name, description, language):
                items.append(it)
        except Exception as e:
            log.warning("github trending parse fail: %s", e)

    # Already sorted by GitHub's own trending algorithm (new stars first).
    return items[:limit]


def _parse_count(el) -> int:
    if el is None:
        return 0
    txt = el.get_text(" ", strip=True).split()
    if not txt:
        return 0
    return _to_int(txt[0])


def _parse_new_stars(row) -> int:
    """The trending row ends with e.g. '1,234 stars this week' / 'today' / 'month'."""
    # GitHub uses class names like float-sm-right or d-inline-block.
    candidates = row.select("span.d-inline-block, span.float-sm-right")
    for span in candidates:
        txt = span.get_text(" ", strip=True)
        m = re.search(r"([\d,]+)\s+stars?\s+(today|this\s+week|this\s+month)", txt, re.I)
        if m:
            return _to_int(m.group(1))
    return 0


def _to_int(s: str) -> int:
    s = s.replace(",", "").strip()
    return int(s) if s.isdigit() else 0


def _is_ai_relevant(full_name: str, description: str, language: str | None) -> bool:
    haystack = " ".join(filter(None, [full_name, description, language or ""])).lower()
    return any(kw in haystack for kw in AI_KEYWORDS)
