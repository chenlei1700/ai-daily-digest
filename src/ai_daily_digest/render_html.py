"""Render the categorized HTML brief."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .models import Item, CATEGORIES, CATEGORY_LABELS


def render(
    items: list[Item],
    date_str: str,
    deduped_count: int,
    template_dir: Path,
    output_path: Path,
    reddit_status: str = "unknown",
) -> None:
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html"]),
    )
    by_cat: dict[str, list[Item]] = {c: [] for c in CATEGORIES}
    for it in items:
        by_cat.setdefault(it.category, []).append(it)
    for lst in by_cat.values():
        lst.sort(key=lambda i: i.score, reverse=True)

    categories = [
        {
            "key": c,
            "label": CATEGORY_LABELS[c],
            "entries": [_view(i) for i in by_cat[c]],
        }
        for c in CATEGORIES
    ]
    html = env.get_template("digest.html").render(
        date=date_str,
        total_items=len(items),
        deduped_count=deduped_count,
        categories=categories,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        reddit_status=reddit_status,
        reddit_login_required=(reddit_status == "login_required"),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def _view(it: Item) -> dict:
    main_summary, hype = _split_hype(it.llm_summary)
    return {
        "title": it.title_zh or it.title,
        "title_original": it.title if (it.title_zh and it.title_zh != it.title) else None,
        "url": it.url,
        "source": it.source,
        "author": it.author,
        "published_at": it.published_at.isoformat() if it.published_at else None,
        "raw_metrics": it.raw_metrics,
        "summary": it.summary,
        "llm_summary": main_summary,
        "hype_note": hype,
        "score": it.score,
    }


def _split_hype(text: str | None) -> tuple[str | None, str | None]:
    """Pull the trailing `⚠️ [hype: ...]` line out so it can be styled separately."""
    if not text:
        return text, None
    lines = text.strip().splitlines()
    for i in range(len(lines) - 1, -1, -1):
        ln = lines[i].strip()
        if ln.startswith("⚠️") and "[hype:" in ln:
            return "\n".join(lines[:i]).strip(), ln
    return text, None
