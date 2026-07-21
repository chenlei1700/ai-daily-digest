"""Prepare bounded summary slices and merge model-written summary parts."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_BRIEF_CONTENT_CHARS = 6_000
DEFAULT_SLICE_CHAR_BUDGET = 40_000
DEFAULT_SLICE_MAX_ITEMS = 8
DEFAULT_MAX_PARALLEL_AGENTS = 6
MAX_PARALLEL_AGENTS_LIMIT = 6

_FALLBACK_MARKER = "摘要生成失败"
_REQUIRED_SUMMARY_FIELDS = (
    "title_zh",
    "summary",
    "content_sha256",
    "source_version",
)


def compact_pending_item(item: dict[str, Any], brief_content_chars: int) -> dict[str, Any]:
    """Bound brief-mode input while preserving full-page evidence metadata."""
    compacted = copy.deepcopy(item)
    content = compacted.setdefault("content", {})
    text = str(content.get("text") or "")
    full_chars = int(
        content.get("full_content_chars")
        or content.get("content_chars")
        or len(text)
    )

    if compacted.get("summary_mode") == "brief":
        text = _leading_excerpt(text, brief_content_chars)

    content["text"] = text
    content["content_chars"] = len(text)
    content["full_content_chars"] = full_chars
    content["is_excerpt"] = len(text) < full_chars
    if content["is_excerpt"]:
        content["excerpt_policy"] = "leading_verified_text"
    else:
        content.pop("excerpt_policy", None)
    return compacted


def write_summary_slices(
    pending: dict[str, Any],
    pending_path: Path,
    output_dir: Path,
    *,
    brief_content_chars: int = DEFAULT_BRIEF_CONTENT_CHARS,
    slice_char_budget: int = DEFAULT_SLICE_CHAR_BUDGET,
    slice_max_items: int = DEFAULT_SLICE_MAX_ITEMS,
    max_parallel_agents: int = DEFAULT_MAX_PARALLEL_AGENTS,
) -> tuple[dict[str, Any], Path]:
    """Write category-local slices sized by serialized input, not item count alone."""
    _require_positive("brief_content_chars", brief_content_chars)
    _require_positive("slice_char_budget", slice_char_budget)
    _require_positive("slice_max_items", slice_max_items)
    _require_positive("max_parallel_agents", max_parallel_agents)
    if max_parallel_agents > MAX_PARALLEL_AGENTS_LIMIT:
        raise ValueError(
            f"max_parallel_agents must be <= {MAX_PARALLEL_AGENTS_LIMIT}"
        )

    date_str = str(pending.get("date") or "")
    if not date_str:
        raise ValueError("pending data has no date")
    raw_items = pending.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("pending data has no items list")

    items = [compact_pending_item(item, brief_content_chars) for item in raw_items]
    by_category: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        category = str(item.get("category") or "unknown")
        by_category.setdefault(category, []).append(item)

    output_dir.mkdir(parents=True, exist_ok=True)
    slices_dir = output_dir / "slices" / date_str
    slices_dir.mkdir(parents=True, exist_ok=True)
    for stale in slices_dir.glob("*.json"):
        stale.unlink()
    for stale in output_dir.glob(f"digest-{date_str}.summaries.part-*.json"):
        stale.unlink()

    slice_specs: list[dict[str, Any]] = []
    for category, category_items in by_category.items():
        category_items.sort(
            key=lambda item: (
                item.get("summary_mode") != "deep",
                -float(item.get("score") or 0),
            )
        )
        packed = _pack_items(category_items, slice_char_budget, slice_max_items)
        safe_category = re.sub(r"[^a-zA-Z0-9_-]+", "-", category).strip("-") or "unknown"
        for index, slice_items in enumerate(packed, start=1):
            slice_id = f"{safe_category}-{index:02d}"
            input_path = slices_dir / f"{slice_id}.json"
            output_path = output_dir / f"digest-{date_str}.summaries.part-{slice_id}.json"
            payload = {
                "date": date_str,
                "slice_id": slice_id,
                "category": category,
                "items": slice_items,
            }
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            input_path.write_text(serialized, encoding="utf-8")
            item_chars = sum(_serialized_chars(item) for item in slice_items)
            slice_specs.append({
                "id": slice_id,
                "category": category,
                "input_path": str(input_path),
                "output_path": str(output_path),
                "items": len(slice_items),
                "deep": sum(item.get("summary_mode") == "deep" for item in slice_items),
                "brief": sum(item.get("summary_mode") == "brief" for item in slice_items),
                "input_chars": item_chars,
                "file_chars": len(serialized),
                "oversized": item_chars > slice_char_budget,
                "urls": [item["url"] for item in slice_items],
            })

    manifest = {
        "date": date_str,
        "pending_path": str(pending_path),
        "total_items": len(items),
        "deep_items": sum(item.get("summary_mode") == "deep" for item in items),
        "brief_items": sum(item.get("summary_mode") == "brief" for item in items),
        "brief_excerpt_items": sum(
            bool(item.get("content", {}).get("is_excerpt")) for item in items
        ),
        "brief_content_chars": brief_content_chars,
        "slice_char_budget": slice_char_budget,
        "slice_max_items": slice_max_items,
        "recommended_parallel_agents": max_parallel_agents,
        "slice_count": len(slice_specs),
        "slices": slice_specs,
    }
    manifest_path = slices_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest, manifest_path


def merge_summary_parts(manifest_path: Path, summaries_path: Path) -> dict[str, Any]:
    """Validate every expected part and atomically write a complete summaries file."""
    manifest = _load_json_object(manifest_path)
    slice_specs = manifest.get("slices")
    if not isinstance(slice_specs, list):
        raise ValueError("slice manifest has no slices list")

    merged: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    expected_urls: set[str] = set()

    for spec in slice_specs:
        slice_id = str(spec.get("id") or "unknown")
        input_path = Path(str(spec.get("input_path") or ""))
        output_path = Path(str(spec.get("output_path") or ""))
        try:
            slice_payload = _load_json_object(input_path)
            slice_items = slice_payload.get("items")
            if not isinstance(slice_items, list):
                raise ValueError("slice has no items list")
            expected = {str(item["url"]): item for item in slice_items}
            duplicate_expected = expected_urls.intersection(expected)
            if duplicate_expected:
                raise ValueError(f"duplicate expected urls: {sorted(duplicate_expected)}")
            expected_urls.update(expected)

            part = _load_json_object(output_path)
            actual_urls = set(part)
            missing = sorted(set(expected) - actual_urls)
            extra = sorted(actual_urls - set(expected))
            reasons: list[str] = []
            if missing:
                reasons.append(f"missing urls: {missing}")
            if extra:
                reasons.append(f"unexpected urls: {extra}")

            valid_entries: dict[str, dict[str, Any]] = {}
            for url, item in expected.items():
                if url not in part:
                    continue
                entry_errors = _validate_summary_entry(part[url], item)
                if entry_errors:
                    reasons.append(f"{url}: {', '.join(entry_errors)}")
                else:
                    valid_entries[url] = part[url]

            if reasons:
                failures.append({"slice_id": slice_id, "reasons": reasons})
                continue
            merged.update(valid_entries)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append({"slice_id": slice_id, "reasons": [str(exc)]})

    globally_missing = sorted(expected_urls - set(merged))
    if globally_missing and not failures:
        failures.append({"slice_id": "manifest", "reasons": [
            f"missing urls after merge: {globally_missing}"
        ]})

    report = {
        "ok": not failures and len(merged) == int(manifest.get("total_items") or 0),
        "date": manifest.get("date"),
        "expected": int(manifest.get("total_items") or 0),
        "merged": len(merged),
        "failed_slices": failures,
        "summaries_path": str(summaries_path),
    }
    report_path = manifest_path.parent / "merge-report.json"

    if report["ok"]:
        summaries_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = summaries_path.with_suffix(summaries_path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary_path.replace(summaries_path)

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def _leading_excerpt(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    candidate = text[:limit]
    minimum = int(limit * 0.8)
    boundary = max(candidate.rfind("\n", minimum), candidate.rfind(" ", minimum))
    if boundary >= minimum:
        candidate = candidate[:boundary]
    return candidate.rstrip()


def _pack_items(
    items: list[dict[str, Any]],
    char_budget: int,
    max_items: int,
) -> list[list[dict[str, Any]]]:
    packed: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for item in items:
        item_chars = _serialized_chars(item)
        would_overflow = current and current_chars + item_chars > char_budget
        if would_overflow or len(current) >= max_items:
            packed.append(current)
            current = []
            current_chars = 0
        current.append(item)
        current_chars += item_chars
    if current:
        packed.append(current)
    return packed


def _serialized_chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"file missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path.name}")
    return data


def _validate_summary_entry(entry: Any, item: dict[str, Any]) -> list[str]:
    if not isinstance(entry, dict):
        return ["entry is not an object"]
    errors = []
    for field in _REQUIRED_SUMMARY_FIELDS:
        value = entry.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field} is missing or empty")
    if _FALLBACK_MARKER in str(entry.get("summary") or ""):
        errors.append("summary is a fallback placeholder")

    content = item.get("content") or {}
    if entry.get("content_sha256") != content.get("content_sha256"):
        errors.append("content_sha256 mismatch")
    if entry.get("source_version") != content.get("source_version"):
        errors.append("source_version mismatch")
    return errors


def _require_positive(name: str, value: int) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")
