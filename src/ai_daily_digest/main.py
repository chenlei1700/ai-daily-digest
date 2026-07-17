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


def _summary_part_paths(date_str: str) -> list[Path]:
    return sorted(OUTPUT_DIR.glob(f"digest-{date_str}.summaries.part-*.json"))


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
    learning_items = [it for it in raw_items if it.raw_metrics.get("learning_card")]
    news_items = [it for it in raw_items if not it.raw_metrics.get("learning_card")]
    fresh = learning_items + store.filter_new(news_items)
    deduped_count = len(raw_items) - len(fresh)
    log.info("after dedup: %d fresh items (%d filtered as already-seen)",
             len(fresh), deduped_count)

    # 3. score
    for it in fresh:
        it.score = scoring.score_item(it)

    # 4. persist items + pending list
    date_str = on_date.isoformat()
    items_data = {
        "date": date_str,
        "deduped_count": deduped_count,
        "reddit_status": reddit_source.LAST_STATUS,
        "items": [it.to_dict() for it in fresh],
    }
    _items_path(date_str).write_text(
        json.dumps(items_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # All fresh items go into pending.json. Top-K are marked "deep" (four-section
    # summary); the rest are "brief" (single-sentence Chinese description).
    deep_set = {it.url for it in _select_for_summary(fresh, top_k_summary)}
    pending_data = {
        "date": date_str,
        "note": "Claude reads this, writes back to summaries.json — see SKILL.md.",
        "schema": {
            "summary_mode": "'deep' → write 4-section summary; 'brief' → 1-sentence Chinese.",
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

    # 5. record as seen — only items that get a deep summary count as "shown".
    # Brief items aren't recorded, so they can re-surface and get another shot at
    # top-K tomorrow. Prevents the failure mode where a slow-moving source (e.g.
    # HF Daily Papers) gets fully consumed on day 1 and shows 0 items on day 2.
    deep_items = [
        it for it in fresh
        if it.url in deep_set and not it.raw_metrics.get("learning_card")
    ]
    store.record(deep_items, on_date)

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
    summaries, fallback_count = _load_or_recover_summaries(date_str, items, summaries_file)
    applied = 0
    if summaries:
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

    # Surface fallback usage loudly. A high ratio means the summarize step
    # (Claude writing summaries.json) failed or was skipped — the digest will
    # render, but every card reads "信息有限，需读原文". Don't let this pass silently.
    real = applied - fallback_count
    if fallback_count:
        ratio = fallback_count / applied if applied else 1.0
        level = log.error if ratio >= 0.5 else log.warning
        level(
            "⚠️  %d/%d summaries are FALLBACK placeholders (%.0f%%). "
            "The summarize step likely failed — check summaries.json.",
            fallback_count, applied, ratio * 100,
        )

    print(
        f"\nDIGEST_READY html={_html_path(date_str)} wiki={_wiki_path(date_str)} "
        f"items={len(items)} deduped={deduped_count} summaries_applied={applied} "
        f"real={real} fallback={fallback_count}"
    )
    return 0


def _load_or_recover_summaries(
    date_str: str,
    items: list[Item],
    summaries_file: Path,
) -> tuple[dict, int]:
    """Load summaries, or recover from part files and fallback summaries.

    Background launches can fail halfway through large JSON writes. Rather than
    rendering an empty digest, keep every valid summary part and synthesize a
    conservative learning-oriented fallback for missing items.

    Returns (summaries, fallback_count) so the caller can report how much of the
    digest is real vs placeholder text.
    """
    summaries: dict = {}
    if summaries_file.exists():
        try:
            data = json.loads(summaries_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                summaries.update(data)
        except Exception as e:
            log.warning("summaries.json invalid; trying part files: %s", e)

    for part in _summary_part_paths(date_str):
        try:
            data = json.loads(part.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key, entry in data.items():
                    # A complete summaries file is authoritative. Part files
                    # only recover absent or previously synthesized entries.
                    if key not in summaries or _is_fallback_summary(summaries[key]):
                        summaries[key] = entry
        except Exception as e:
            log.warning("summary part invalid, skipped: %s (%s)", part.name, e)

    missing = 0
    for it in items:
        if it.url in summaries or it.dedup_key() in summaries:
            continue
        summaries[it.url] = _fallback_summary(it)
        missing += 1

    if summaries:
        summaries_file.write_text(
            json.dumps(summaries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if missing:
            log.warning("filled %d missing summaries with fallback text", missing)

    # Count fallback text across the *whole* set, not just the ones we just
    # synthesized. This catches the failure mode where a prior step wrote a
    # complete-but-placeholder summaries.json (every card = "信息有限，需读原文"),
    # which the `missing` counter alone would report as 0.
    fallback_count = 0
    for it in items:
        entry = summaries.get(it.url) or summaries.get(it.dedup_key())
        if _is_fallback_summary(entry):
            fallback_count += 1

    return summaries, fallback_count


# Sentinel phrase every fallback summary contains; used to detect a
# summaries.json that is structurally complete but semantically empty.
_FALLBACK_MARKER = "信息有限，需读原文"


def _is_fallback_summary(entry) -> bool:
    if isinstance(entry, str):
        text = entry
    elif isinstance(entry, dict):
        text = entry.get("summary") or ""
    else:
        return False
    return _FALLBACK_MARKER in text


def _fallback_summary(it: Item) -> dict[str, str]:
    label = CATEGORY_LABELS.get(it.category, it.category)
    title_zh = it.title
    raw = (it.summary or "").strip()
    basis = raw[:160] if raw else f"原始信息主要来自标题：{it.title}"

    if it.category == "pm_practice":
        concept = "这条内容适合用来练习把用户任务、输入输出、流程节点、人工确认和成功指标写进 PRD。"
        pm_use = "阅读时重点标出用户要完成的任务、AI 参与的环节、失败时的兜底入口，以及可以验证价值的指标。"
    elif it.category == "model_limits":
        concept = "这条内容适合用来理解大模型边界：模型可能会出错、越权、误解上下文，或者在长上下文中丢失关键信息。"
        pm_use = "阅读时重点追问哪些场景不能全自动、哪些输出需要引用或人工确认，以及失败后用户如何纠错。"
    elif it.category == "ai_evals":
        concept = "这条内容适合用来学习 AI 评测：先定义任务成功，再设计样本、指标、人工复核和上线门槛。"
        pm_use = "阅读时重点把它转成一个小评测集：输入是什么、好答案标准是什么、错误答案如何判定。"
    elif it.category == "arxiv":
        concept = "这条内容来自研究进展，产品经理不必先看公式，应该先判断它可能带来什么新能力或新限制。"
        pm_use = "阅读时重点追问它能改善哪个用户任务、落地还缺什么条件、是否需要评测集验证。"
    elif it.category in ("github_trending", "claude_code", "codex"):
        concept = "这条内容来自工具或平台变化，适合观察 AI 如何改变具体工作流。"
        pm_use = "阅读时重点判断它减少了哪一步人工操作、引入了什么权限或可靠性风险、是否值得纳入竞品分析。"
    else:
        concept = "这条内容适合用于建立行业判断：哪些能力在变强，哪些成本、监管、竞品或用户心智正在变化。"
        pm_use = "阅读时重点记录它对产品机会、风险、定价、渠道或用户需求优先级的影响。"

    if it.raw_metrics.get("learning_card"):
        happened = basis
    else:
        happened = f"信息有限，需读原文。这是一条「{label}」相关内容：{it.title}"

    return {
        "title_zh": title_zh,
        "summary": (
            f"① **发生了什么**：{happened}\n"
            f"② **你要学的概念**：{concept}\n"
            f"③ **产品经理怎么用**：{pm_use}\n"
            f"④ **可以追问的问题**：这件事对应的真实用户任务是什么？上线前要用什么指标证明它真的有用？"
        ),
    }


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
