"""GitHub Trending — scrapes the public /trending HTML page.

The Search API can't tell us *trending* (it only sorts by cumulative stars),
so we parse the official trending page. We pull from BOTH `since=daily` and
`since=weekly` and merge by repo URL:
  - daily surfaces newly hot repos (avoids the dedup wipeout when weekly-only
    repeats the same projects for 5+ days)
  - weekly keeps higher-quality projects that built sustained momentum

We filter to AI-relevant rows after scraping (no official topic filter on
the trending page — we approximate via keyword match against title +
description + language).
"""
from __future__ import annotations

import logging
import os
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
API_HEADERS = {"Accept": "application/vnd.github+json"}


def fetch(limit: int = 30, since: str | None = None) -> list[Item]:
    """Fetch trending repos.

    If `since` is None (default), pulls daily + weekly and merges by URL,
    preferring the daily entry when both windows surface the same repo.
    Pass an explicit `since` ("daily" / "weekly" / "monthly") to fetch one window.
    """
    if since is not None:
        return _fetch_one(since, limit)

    daily = _fetch_one("daily", limit)
    weekly = _fetch_one("weekly", limit)

    by_url: dict[str, Item] = {}
    for it in daily:
        by_url[it.url] = it
    for it in weekly:
        by_url.setdefault(it.url, it)

    merged = list(by_url.values())
    merged.sort(
        key=lambda it: (
            0 if it.raw_metrics.get("trending_period") == "daily" else 1,
            -(it.raw_metrics.get("new_stars") or 0),
        )
    )
    return merged[:limit]


def _fetch_one(since: str, limit: int) -> list[Item]:
    items: list[Item] = []
    api_headers = dict(API_HEADERS)
    if token := os.getenv("GITHUB_TOKEN"):
        api_headers["Authorization"] = f"Bearer {token}"

    try:
        with httpx.Client(timeout=20.0, headers=HEADERS, follow_redirects=True) as client:
            r = client.get(TRENDING_URL, params={"since": since})
            r.raise_for_status()

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

                    if not _is_ai_relevant(full_name, description, language):
                        continue

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

                    items.append(it)
                except Exception as e:
                    log.warning("github trending parse fail: %s", e)
    except Exception as e:
        log.warning("github trending fetch failed (since=%s): %s", since, e)
        return []

    # Already sorted by GitHub's own trending algorithm (new stars first).
    items = items[:limit]
    _attach_repo_metadata(items, api_headers)
    return items


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


def _attach_repo_metadata(items: list[Item], headers: dict[str, str]) -> None:
    if not items:
        return
    try:
        with httpx.Client(timeout=15.0, headers=headers) as client:
            for it in items:
                full_name = it.url.removeprefix("https://github.com/")
                try:
                    r = client.get(f"https://api.github.com/repos/{full_name}")
                    r.raise_for_status()
                    data = r.json()
                    it.raw_metrics["pushed_at"] = data.get("pushed_at")
                    it.raw_metrics["updated_at"] = data.get("updated_at")
                except Exception as e:
                    log.warning("github repo metadata fetch failed (%s): %s", full_name, e)
    except Exception as e:
        log.warning("github repo metadata client fail: %s", e)


def _is_ai_relevant(full_name: str, description: str, language: str | None) -> bool:
    haystack = " ".join(filter(None, [full_name, description, language or ""])).lower()
    return any(kw in haystack for kw in AI_KEYWORDS)
