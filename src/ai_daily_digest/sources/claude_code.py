"""Claude Code updates — official releases + community plugins.

Sources:
  1. anthropics/claude-code GitHub releases (authoritative)
  2. Recent commits to anthropics/claude-code (catches docs/feature changes
     between releases)
  3. GitHub Atom feeds as a no-API fallback for release/commit visibility
  4. npm package versions as a non-GitHub release fallback
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

import feedparser
import httpx
from dateutil import parser as date_parser

from ..models import Item

log = logging.getLogger(__name__)

REPO = "anthropics/claude-code"
NPM_PACKAGE_URL = "https://registry.npmjs.org/@anthropic-ai%2Fclaude-code"


def fetch(limit: int = 30) -> list[Item]:
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    # Releases have higher signal than commits — give them ~40% of the budget.
    rel_n = max(3, int(limit * 0.4))
    com_n = max(2, limit - rel_n)
    items: list[Item] = []
    with httpx.Client(timeout=15.0, headers=headers, follow_redirects=True) as client:
        releases = _releases(client, rel_n)
        commits = _recent_commits(client, com_n)
        if not releases:
            releases = _release_feed(client, rel_n)
        if not releases:
            releases = _npm_releases(client, rel_n)
        if not commits:
            commits = _commit_feed(client, com_n)
        items.extend(releases)
        items.extend(commits)
    return items


def _releases(client: httpx.Client, limit: int) -> list[Item]:
    try:
        r = client.get(
            f"https://api.github.com/repos/{REPO}/releases",
            params={"per_page": limit},
        )
        r.raise_for_status()
        out = []
        for rel in r.json():
            out.append(
                Item(
                    category="claude_code",
                    title=f"Release {rel['tag_name']}: {rel.get('name') or ''}".strip(),
                    url=rel["html_url"],
                    source="claude-code releases",
                    published_at=_parse_iso(rel.get("published_at")),
                    summary=(rel.get("body") or "")[:1500],
                    raw_metrics={"tag": rel["tag_name"], "is_prerelease": rel.get("prerelease", False)},
                )
            )
        return out
    except Exception as e:
        log.warning("claude_code releases fail: %s", e)
        return []


def _recent_commits(client: httpx.Client, limit: int) -> list[Item]:
    try:
        r = client.get(
            f"https://api.github.com/repos/{REPO}/commits",
            params={"per_page": limit},
        )
        r.raise_for_status()
        out = []
        for c in r.json():
            msg = (c.get("commit", {}).get("message") or "").split("\n")[0][:200]
            out.append(
                Item(
                    category="claude_code",
                    title=f"commit: {msg}",
                    url=c["html_url"],
                    source="claude-code commits",
                    published_at=_parse_iso(c["commit"]["author"]["date"]),
                    author=(c.get("author") or {}).get("login"),
                    raw_metrics={"sha": c["sha"][:7]},
                )
            )
        return out
    except Exception as e:
        log.warning("claude_code commits fail: %s", e)
        return []


def _release_feed(client: httpx.Client, limit: int) -> list[Item]:
    try:
        r = client.get(f"https://github.com/{REPO}/releases.atom")
        r.raise_for_status()
        out = []
        for entry in feedparser.parse(r.text).entries[:limit]:
            title = entry.get("title", "").strip()
            url = _entry_link(entry)
            if not title or not url:
                continue
            tag = url.rstrip("/").rsplit("/", 1)[-1]
            out.append(
                Item(
                    category="claude_code",
                    title=f"Release {tag}: {title}".strip(),
                    url=url,
                    source="claude-code releases feed",
                    published_at=_parse_feed_date(entry),
                    summary=(entry.get("summary") or "")[:1500],
                    raw_metrics={"tag": tag, "is_prerelease": False},
                )
            )
        return out
    except Exception as e:
        log.warning("claude_code releases feed fail: %s", e)
        return []


def _commit_feed(client: httpx.Client, limit: int) -> list[Item]:
    try:
        r = client.get(f"https://github.com/{REPO}/commits/main.atom")
        r.raise_for_status()
        out = []
        for entry in feedparser.parse(r.text).entries[:limit]:
            title = entry.get("title", "").split("\n")[0][:200]
            url = _entry_link(entry)
            if not title or not url:
                continue
            sha = url.rstrip("/").rsplit("/", 1)[-1][:7]
            author = None
            if entry.get("author_detail"):
                author = entry.author_detail.get("name")
            out.append(
                Item(
                    category="claude_code",
                    title=f"commit: {title}",
                    url=url,
                    source="claude-code commits feed",
                    published_at=_parse_feed_date(entry),
                    author=author,
                    raw_metrics={"sha": sha},
                )
            )
        return out
    except Exception as e:
        log.warning("claude_code commits feed fail: %s", e)
        return []


def _npm_releases(client: httpx.Client, limit: int) -> list[Item]:
    try:
        r = client.get(NPM_PACKAGE_URL)
        r.raise_for_status()
        data = r.json()
        times = data.get("time", {})
        versions = [
            (version, times.get(version))
            for version in data.get("versions", {})
            if version not in {"created", "modified"} and times.get(version)
        ]
        versions.sort(key=lambda row: row[1], reverse=True)

        out = []
        for version, published in versions[:limit]:
            package = data["versions"].get(version, {})
            body = package.get("description") or data.get("description") or ""
            out.append(
                Item(
                    category="claude_code",
                    title=f"Release v{version}: npm package @anthropic-ai/claude-code",
                    url=f"https://github.com/{REPO}/releases/tag/v{version}",
                    source="claude-code npm releases",
                    published_at=_parse_iso(published),
                    summary=body[:1500],
                    raw_metrics={"tag": f"v{version}", "is_prerelease": "-" in version},
                )
            )
        return out
    except Exception as e:
        log.warning("claude_code npm releases fail: %s", e)
        return []


def _entry_link(entry) -> str | None:
    if entry.get("link"):
        return entry.link
    for link in entry.get("links", []):
        href = link.get("href")
        if href:
            return href
    return None


def _parse_feed_date(entry):
    for key in ("published", "updated"):
        if value := entry.get(key):
            return date_parser.parse(value)
    return None


def _parse_iso(s: str | None):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))
