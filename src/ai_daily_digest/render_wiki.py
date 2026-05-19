"""Markdown wiki entry — one file per day, organized by category.

Why markdown alongside HTML: text is grep-able, diff-able, and survives any
editor/viewer. The HTML is for daily reading; the wiki is for "what did I learn
in March?" archeology.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .models import Item, CATEGORIES, CATEGORY_LABELS


def render(items: list[Item], date_str: str, output_path: Path) -> None:
    by_cat: dict[str, list[Item]] = {c: [] for c in CATEGORIES}
    for it in items:
        by_cat.setdefault(it.category, []).append(it)
    for lst in by_cat.values():
        lst.sort(key=lambda i: i.score, reverse=True)

    lines: list[str] = []
    lines.append(f"# AI Daily Digest — {date_str}")
    lines.append("")
    lines.append(
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · {len(items)} items total_"
    )
    lines.append("")
    lines.append("## Contents")
    for c in CATEGORIES:
        n = len(by_cat.get(c, []))
        lines.append(f"- [{CATEGORY_LABELS[c]}](#{c}) ({n})")
    lines.append("")

    for c in CATEGORIES:
        lst = by_cat.get(c, [])
        lines.append(f"## <a id='{c}'></a>{CATEGORY_LABELS[c]}")
        lines.append("")
        if not lst:
            lines.append("_无新内容_")
            lines.append("")
            continue
        for it in lst:
            if it.title_zh and it.title_zh != it.title:
                heading = f"### [{it.title_zh}]({it.url})\n_原文标题：{it.title}_"
            else:
                heading = f"### [{it.title}]({it.url})"
            lines.append(heading)
            meta = [f"score: {it.score:.1f}", f"source: {it.source}"]
            if it.author:
                meta.append(f"by {it.author}")
            if it.published_at:
                meta.append(it.published_at.strftime("%Y-%m-%d"))
            if "points" in it.raw_metrics:
                meta.append(f"{it.raw_metrics['points']} HN pts")
            if "stars" in it.raw_metrics:
                meta.append(f"★{it.raw_metrics['stars']}")
            lines.append("_" + " · ".join(meta) + "_")
            lines.append("")
            if it.llm_summary:
                lines.append(it.llm_summary)
                lines.append("")
            elif it.summary:
                snippet = it.summary[:400].strip()
                lines.append(f"> {snippet}{'…' if len(it.summary) > 400 else ''}")
                lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
