"""Claude Code updates — official releases + community plugins.

Sources:
  1. anthropics/claude-code GitHub releases (authoritative)
  2. Recent commits to anthropics/claude-code (catches docs/feature changes
     between releases)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

import httpx

from ..models import Item

log = logging.getLogger(__name__)

REPO = "anthropics/claude-code"


def fetch(limit: int = 30) -> list[Item]:
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    # Releases have higher signal than commits — give them ~40% of the budget.
    rel_n = max(3, int(limit * 0.4))
    com_n = max(2, limit - rel_n)
    items: list[Item] = []
    with httpx.Client(timeout=15.0, headers=headers) as client:
        items.extend(_releases(client, rel_n))
        items.extend(_recent_commits(client, com_n))
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


def _parse_iso(s: str | None):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))
