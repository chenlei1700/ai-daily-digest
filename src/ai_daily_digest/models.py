"""Shared data model for items collected from any source."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


@dataclass
class Item:
    category: str
    title: str
    url: str
    source: str
    published_at: datetime | None = None
    author: str | None = None
    summary: str | None = None
    raw_metrics: dict[str, Any] = field(default_factory=dict)
    content: str | None = None
    source_version: str | None = None
    retrieved_at: datetime | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    title_zh: str | None = None       # filled in by Claude in skill mode
    llm_summary: str | None = None    # filled in by Claude in skill mode

    def dedup_key(self) -> str:
        return self.url.split("#")[0].rstrip("/").lower()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.published_at is not None:
            d["published_at"] = self.published_at.isoformat()
        if self.retrieved_at is not None:
            d["retrieved_at"] = self.retrieved_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Item":
        d = dict(d)
        for key in ("published_at", "retrieved_at"):
            value = d.get(key)
            if isinstance(value, str):
                d[key] = datetime.fromisoformat(value)
        return cls(**d)


CATEGORIES = [
    "pm_practice",
    "model_limits",
    "ai_evals",
    "arxiv",
    "ai_news",
    "github_trending",
    "llm_updates",
    "claude_code",
    "codex",
]

CATEGORY_LABELS = {
    "pm_practice": "AI 产品方法",
    "model_limits": "大模型边界",
    "ai_evals": "AI 评测",
    "arxiv": "重要论文",
    "ai_news": "AI 新闻",
    "github_trending": "GitHub 热门",
    "llm_updates": "大模型动态",
    "claude_code": "Claude Code",
    "codex": "Codex",
}
