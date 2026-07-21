"""Auto-updating, source-tiered learning feeds for junior AI product managers."""
from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

from ..models import Item

log = logging.getLogger(__name__)

SOURCE_CONFIG_VERSION = "2026-07-20.1"
FEEDS = (
    {
        "publisher": "OpenAI",
        "url": "https://openai.com/news/rss.xml",
        "tier": "S",
    },
    {
        "publisher": "Google DeepMind",
        "url": "https://deepmind.google/blog/rss.xml",
        "tier": "S",
    },
    {
        "publisher": "Microsoft Research",
        "url": "https://www.microsoft.com/en-us/research/feed/",
        "tier": "S",
    },
    {
        "publisher": "Hugging Face",
        "url": "https://huggingface.co/blog/feed.xml",
        "tier": "A",
    },
    {
        "publisher": "LangChain",
        "url": "https://blog.langchain.com/rss/",
        "tier": "A",
    },
    {
        "publisher": "Simon Willison",
        "url": "https://simonwillison.net/atom/everything/",
        "tier": "B",
    },
)

TRACKS = {
    "pm_practice": {
        "keywords": (
            "product", "user", "ux", "design", "workflow", "copilot",
            "agent", "human-in-the-loop", "deployment", "enterprise",
            "产品", "用户", "工作流",
        ),
    },
    "model_limits": {
        "keywords": (
            "hallucination", "prompt injection", "jailbreak", "safety",
            "security", "privacy", "context", "memory", "reliability",
            "alignment", "risk", "failure", "limitation", "幻觉", "安全",
        ),
    },
    "ai_evals": {
        "keywords": (
            "eval", "evaluation", "benchmark", "judge", "red team",
            "testing", "metric", "quality", "monitoring", "assessment",
            "评测", "基准", "指标",
        ),
    },
}

_FEED_CACHE: dict[str, tuple[dict, list[dict]]] = {}


def fetch_pm_practice(limit: int = 30) -> list[Item]:
    return _fetch_track("pm_practice", limit)


def fetch_model_limits(limit: int = 30) -> list[Item]:
    return _fetch_track("model_limits", limit)


def fetch_ai_evals(limit: int = 30) -> list[Item]:
    return _fetch_track("ai_evals", limit)


def _fetch_track(category: str, limit: int) -> list[Item]:
    keywords = TRACKS[category]["keywords"]
    candidates: list[tuple[int, datetime | None, Item]] = []
    with ThreadPoolExecutor(max_workers=len(FEEDS)) as pool:
        loaded = list(pool.map(_load_feed, FEEDS))
    for source, (feed_meta, entries) in zip(FEEDS, loaded):
        for entry in entries:
            title = _plain(entry.get("title", ""))
            summary = _plain(entry.get("summary", ""))
            url = _entry_url(entry)
            if not title or not url:
                continue
            haystack = f"{title} {summary}".lower()
            hits = sorted({kw for kw in keywords if kw.lower() in haystack})
            if not hits:
                continue
            published_at = _entry_date(entry)
            entry_updated_at = _entry_updated(entry)
            if published_at and published_at < datetime.now(timezone.utc) - timedelta(days=180):
                continue
            item = Item(
                category=category,
                title=title,
                url=url,
                source=source["publisher"],
                published_at=published_at,
                author=_plain(entry.get("author", "")) or None,
                summary=summary[:1500],
                raw_metrics={
                    "learning_material": True,
                    "source_tier": source["tier"],
                    "keyword_hits": hits,
                    "discovery_feed": source["url"],
                    "feed_version": feed_meta["version"],
                    "entry_id": entry.get("id"),
                    "entry_updated_at": entry_updated_at.isoformat() if entry_updated_at else None,
                    "source_config_version": SOURCE_CONFIG_VERSION,
                },
            )
            candidates.append((len(hits), published_at, item))

    candidates.sort(
        key=lambda row: (
            {"S": 3, "A": 2, "B": 1}.get(row[2].raw_metrics["source_tier"], 0),
            row[0],
            _timestamp(row[1]),
        ),
        reverse=True,
    )
    seen: set[str] = set()
    per_source: dict[str, int] = {}
    source_cap = max(2, (limit + 2) // 3)
    result: list[Item] = []
    for _, _, item in candidates:
        key = item.dedup_key()
        if key in seen or per_source.get(item.source, 0) >= source_cap:
            continue
        seen.add(key)
        per_source[item.source] = per_source.get(item.source, 0) + 1
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _load_feed(source: dict) -> tuple[dict, list[dict]]:
    url = source["url"]
    if url in _FEED_CACHE:
        return _FEED_CACHE[url]
    try:
        with httpx.Client(
            timeout=18.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (ai-daily-digest/0.2)"},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
        parsed = feedparser.parse(response.content)
        body_hash = hashlib.sha256(response.content).hexdigest()[:16]
        version = response.headers.get("etag") or response.headers.get("last-modified") or f"sha256:{body_hash}"
        result = ({"version": str(version)}, list(parsed.entries))
    except Exception as exc:
        log.warning("learning feed failed (%s): %s", url, exc)
        result = ({"version": "unavailable"}, [])
    _FEED_CACHE[url] = result
    return result


def _entry_url(entry: dict) -> str:
    if entry.get("link"):
        return str(entry["link"])
    for link in entry.get("links", []):
        if link.get("rel") == "alternate" and link.get("href"):
            return str(link["href"])
    return ""


def _entry_date(entry: dict) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc)
    return None


def _entry_updated(entry: dict) -> datetime | None:
    value = entry.get("updated_parsed")
    return datetime(*value[:6], tzinfo=timezone.utc) if value else None


def _plain(value: object) -> str:
    if not value:
        return ""
    return " ".join(str(value).replace("\n", " ").split())


def _timestamp(value: datetime | None) -> float:
    return value.timestamp() if value else 0.0
