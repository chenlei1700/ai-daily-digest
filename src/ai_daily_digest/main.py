"""ai-daily-digest CLI — two-stage pipeline for skill-mode summarization.

Stages:
  collect  →  fetch + dedup + score + dump items.json + pending.json
              (no LLM call; Claude reads pending.json and writes summaries.json)
  apply    →  load items.json + summaries.json + render HTML/wiki

Legacy single-shot mode (with --use-api) is kept for users who set
ANTHROPIC_API_KEY and want Python to do the LLM call. Default is skill mode.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as date_cls, datetime
from pathlib import Path

from . import dedupe, render_html, render_wiki, scoring
from .models import Item, CATEGORIES, CATEGORY_LABELS
from .sources import FETCHERS, MULTI_CATEGORY_FETCHERS
from .sources import reddit as reddit_source

log = logging.getLogger("ai_daily_digest")

ROOT = Path(__file__).resolve().parents[2]  # skill root
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
TEMPLATES_DIR = ROOT / "templates"


# ────────────────────────────── shared utilities ─────────────────────────────


def _setup_logging(quiet: bool) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    if quiet:
        for noisy in ("httpx", "httpcore", "urllib3", "anthropic"):
            logging.getLogger(noisy).setLevel(logging.WARNING)


def _items_path(date_str: str) -> Path:
    return OUTPUT_DIR / f"digest-{date_str}.items.json"


def _pending_path(date_str: str) -> Path:
    return OUTPUT_DIR / f"digest-{date_str}.pending.json"


def _summaries_path(date_str: str) -> Path:
    return OUTPUT_DIR / f"digest-{date_str}.summaries.json"


def _html_path(date_str: str) -> Path:
    return OUTPUT_DIR / f"digest-{date_str}.html"


def _wiki_path(date_str: str) -> Path:
    return DATA_DIR / "wiki" / f"{date_str}.md"


def _select_for_summary(items: list[Item], k_per_cat: int) -> list[Item]:
    """Top-K per category by score — the pool Claude will summarize."""
    by_cat: dict[str, list[Item]] = {}
    for it in items:
        by_cat.setdefault(it.category, []).append(it)
    selected: list[Item] = []
    for lst in by_cat.values():
        lst.sort(key=lambda i: i.score, reverse=True)
        selected.extend(lst[:k_per_cat])
    return selected


# ────────────────────────────── stage: collect ──────────────────────────────


def run_collect(
    categories: list[str],
    limit_per_source: int,
    on_date: date_cls,
    top_k_summary: int,
    quiet: bool,
) -> int:
    _setup_logging(quiet)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    store = dedupe.SeenStore(DATA_DIR / "seen.db")
    log.info("dedup store stats: %s", store.stats())

    # 1. fetch
    raw_items: list[Item] = []
    for cat in categories:
        log.info("fetching %s ...", cat)
        try:
            fetched = FETCHERS[cat](limit=limit_per_source)
            log.info("  → %d items", len(fetched))
            raw_items.extend(fetched)
        except Exception as e:
            log.exception("source %s crashed: %s", cat, e)

    # 1b. multi-category fetchers (e.g. Reddit spans 3 categories per call)
    requested = set(categories)
    for fetcher in MULTI_CATEGORY_FETCHERS:
        name = fetcher.__module__.rsplit(".", 1)[-1]
        log.info("fetching %s (multi-category) ...", name)
        try:
            fetched = fetcher()
            kept = [it for it in fetched if it.category in requested]
            log.info("  → %d items (%d kept after category filter)",
                     len(fetched), len(kept))
            raw_items.extend(kept)
        except Exception as e:
            log.exception("multi-category source %s crashed: %s", name, e)

    # 2. dedup
    fresh = store.filter_new(raw_items)
    deduped_count = len(raw_items) - len(fresh)
    log.info("after dedup: %d fresh items (%d filtered as already-seen)",
             len(fresh), deduped_count)

    # 3. score
    for it in fresh:
        it.score = scoring.score_item(it)

    # 4. persist items + pending list
    date_str = on_date.isoformat()

    # Accumulate across same-day runs: if today's items.json already exists
    # (an earlier collect ran today), merge old items with new ones, keeping
    # the highest score per URL. This way "AI 日报" twice in one day shows
    # both batches in the HTML, not just the latest.
    existing_path = _items_path(date_str)
    accumulated: dict[str, Item] = {}
    if existing_path.exists():
        try:
            prev = json.loads(existing_path.read_text(encoding="utf-8"))
            for d in prev.get("items", []):
                it = Item.from_dict(d)
                accumulated[it.url] = it
        except Exception as e:
            log.warning("could not merge previous items.json (%s); starting fresh", e)
    for it in fresh:
        accumulated[it.url] = it  # new wins on collision
    merged = list(accumulated.values())

    items_data = {
        "date": date_str,
        "deduped_count": deduped_count,
        "reddit_status": reddit_source.LAST_STATUS,
        "items": [it.to_dict() for it in merged],
    }
    _items_path(date_str).write_text(
        json.dumps(items_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # All fresh items go into pending.json. Top-K are marked "deep" (three-section
    # summary); the rest are "brief" (single-sentence Chinese description).
    deep_set = {it.url for it in _select_for_summary(fresh, top_k_summary)}
    pending_data = {
        "date": date_str,
        "note": "Claude reads this, writes back to summaries.json — see SKILL.md.",
        "schema": {
            "summary_mode": "'deep' → write 3-section summary; 'brief' → 1-sentence Chinese.",
            "output_format": "{<url>: {title_zh: str, summary: str}}",
        },
        "items": [
            {
                "url": it.url,
                "dedup_key": it.dedup_key(),
                "category": it.category,
                "category_label": CATEGORY_LABELS.get(it.category, it.category),
                "title": it.title,
                "source": it.source,
                "score": it.score,
                "summary_mode": "deep" if it.url in deep_set else "brief",
                "raw": (it.summary or "")[:1500],
            }
            for it in fresh
        ],
    }
    _pending_path(date_str).write_text(
        json.dumps(pending_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 5. record as seen — collect commits the dedup state.
    store.record(fresh, on_date)

    log.info("items.json   : %s", _items_path(date_str))
    log.info("pending.json : %s (%d items: %d deep + %d brief)",
             _pending_path(date_str), len(fresh), len(deep_set), len(fresh) - len(deep_set))

    # Machine-readable handoff line.
    print(
        f"\nCOLLECT_READY items={len(fresh)} deduped={deduped_count} "
        f"pending={len(fresh)} deep={len(deep_set)} brief={len(fresh) - len(deep_set)} "
        f"items_json={_items_path(date_str)} "
        f"pending_json={_pending_path(date_str)} "
        f"date={date_str}"
    )
    return 0


# ────────────────────────────── stage: apply ─────────────────────────────────


def run_apply(on_date: date_cls, quiet: bool) -> int:
    _setup_logging(quiet)
    date_str = on_date.isoformat()

    items_file = _items_path(date_str)
    if not items_file.exists():
        log.error("items.json missing — run `collect` first: %s", items_file)
        return 3

    items_data = json.loads(items_file.read_text(encoding="utf-8"))
    items = [Item.from_dict(d) for d in items_data["items"]]
    deduped_count = items_data.get("deduped_count", 0)
    reddit_status = items_data.get("reddit_status", "unknown")

    # Merge in Claude-written summaries (optional — apply can run without them).
    # Accepts two value shapes:
    #   {url: "summary text"}                              ← legacy
    #   {url: {"title_zh": "...", "summary": "..."}}       ← current
    summaries_file = _summaries_path(date_str)
    applied = 0
    if summaries_file.exists():
        summaries = json.loads(summaries_file.read_text(encoding="utf-8"))
        for it in items:
            entry = summaries.get(it.url) or summaries.get(it.dedup_key())
            if not entry:
                continue
            if isinstance(entry, str):
                it.llm_summary = entry
            elif isinstance(entry, dict):
                it.title_zh = entry.get("title_zh")
                it.llm_summary = entry.get("summary")
            applied += 1
        log.info("merged %d summaries from %s", applied, summaries_file)
    else:
        log.warning("no summaries.json found at %s — rendering without LLM summaries",
                    summaries_file)

    # Render
    render_html.render(items, date_str, deduped_count, TEMPLATES_DIR,
                       _html_path(date_str), reddit_status=reddit_status)
    render_wiki.render(items, date_str, _wiki_path(date_str))

    log.info("HTML : %s", _html_path(date_str))
    log.info("Wiki : %s", _wiki_path(date_str))

    print(
        f"\nDIGEST_READY html={_html_path(date_str)} wiki={_wiki_path(date_str)} "
        f"items={len(items)} deduped={deduped_count} summaries_applied={applied}"
    )
    return 0


# ────────────────────────────────── CLI ──────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ai-daily-digest")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--quiet", action="store_true")
    common.add_argument("--date", default=None, help="override date YYYY-MM-DD")

    pc = sub.add_parser("collect", parents=[common],
                        help="fetch + dedup + score + emit items.json/pending.json")
    pc.add_argument("--categories", default=",".join(CATEGORIES),
                    help="comma-separated subset of: " + ",".join(CATEGORIES))
    pc.add_argument("--limit-per-source", type=int, default=30)
    pc.add_argument("--top-k-summary", type=int, default=5,
                    help="top-K items per category to include in pending.json")

    sub.add_parser("apply", parents=[common],
                   help="merge summaries.json + render HTML/wiki")

    args = p.parse_args(argv)

    on_date = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date else date_cls.today()
    )

    if args.cmd == "collect":
        cats = [c.strip() for c in args.categories.split(",") if c.strip()]
        bad = [c for c in cats if c not in CATEGORIES]
        if bad:
            print(f"unknown categories: {bad}; valid: {CATEGORIES}", file=sys.stderr)
            return 2
        return run_collect(cats, args.limit_per_source, on_date,
                           args.top_k_summary, args.quiet)
    elif args.cmd == "apply":
        return run_apply(on_date, args.quiet)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
