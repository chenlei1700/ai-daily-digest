"""Validate source links and extract versioned webpage text for summarization."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .models import Item

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; ai-daily-digest/0.2; +https://github.com/1572135825-prog/ai-daily-digest)"
MIN_CONTENT_CHARS = 180
MAX_CONTENT_CHARS = 16_000
MAX_RESPONSE_BYTES = 5_000_000


def enrich_items(
    items: list[Item],
    cache_dir: Path,
    workers: int = 8,
) -> tuple[list[Item], list[dict[str, object]]]:
    """Return only items whose public source page was read successfully."""
    if not items:
        return [], []

    cache_dir.mkdir(parents=True, exist_ok=True)
    valid: list[Item] = []
    failures: list[dict[str, object]] = []
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,text/plain,application/json;q=0.8,*/*;q=0.5",
        "Accept-Language": "en-US,en;q=0.8,zh-CN;q=0.6",
    }

    with httpx.Client(timeout=18.0, headers=headers, follow_redirects=True) as client:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {
                pool.submit(enrich_item, item, client, cache_dir): item
                for item in items
            }
            for future in as_completed(futures):
                item = futures[future]
                try:
                    ok, reason = future.result()
                except Exception as exc:  # isolate one bad page from the digest
                    ok, reason = False, f"unexpected:{type(exc).__name__}"
                    log.warning("content enrichment crashed for %s: %s", item.url, exc)
                if ok:
                    valid.append(item)
                else:
                    failures.append({
                        "url": item.url,
                        "content_url": _content_url(item),
                        "category": item.category,
                        "reason": reason,
                        "http_status": item.provenance.get("http_status"),
                    })

    order = {id(item): idx for idx, item in enumerate(items)}
    valid.sort(key=lambda item: order[id(item)])
    return valid, failures


def enrich_item(
    item: Item,
    client: httpx.Client,
    cache_dir: Path,
) -> tuple[bool, str]:
    """Validate one URL, extract readable text, and attach immutable evidence."""
    content_url = _content_url(item)
    parsed = urlparse(content_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        item.provenance = {"status": "invalid_url", "content_url": content_url}
        return False, "invalid_url"

    cache_key = hashlib.sha256(content_url.encode("utf-8")).hexdigest()
    meta_path = cache_dir / f"{cache_key}.json"
    text_path = cache_dir / f"{cache_key}.txt"
    cached = _load_cache(meta_path, text_path)
    request_headers: dict[str, str] = {}
    if cached:
        if cached[0].get("etag"):
            request_headers["If-None-Match"] = str(cached[0]["etag"])
        if cached[0].get("last_modified"):
            request_headers["If-Modified-Since"] = str(cached[0]["last_modified"])

    retrieved_at = datetime.now(timezone.utc)
    try:
        response = client.get(content_url, headers=request_headers)
    except httpx.HTTPError as exc:
        item.provenance = {
            "status": "fetch_error",
            "content_url": content_url,
            "error": type(exc).__name__,
        }
        return False, f"fetch_error:{type(exc).__name__}"

    if response.status_code == 304 and cached:
        metadata, text = cached
        final_url = str(metadata.get("final_url") or content_url)
        content_type = str(metadata.get("content_type") or "text/html")
        etag = metadata.get("etag")
        last_modified = metadata.get("last_modified")
        cache_state = "revalidated"
    elif 200 <= response.status_code < 300:
        content_length = int(response.headers.get("content-length") or 0)
        if content_length > MAX_RESPONSE_BYTES or len(response.content) > MAX_RESPONSE_BYTES:
            item.provenance = {
                "status": "too_large",
                "content_url": content_url,
                "http_status": response.status_code,
            }
            return False, "response_too_large"
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        text = _extract_text(response, content_type)
        final_url = str(response.url)
        etag = response.headers.get("etag")
        last_modified = response.headers.get("last-modified")
        cache_state = "fresh"
    else:
        item.provenance = {
            "status": "http_error",
            "content_url": content_url,
            "final_url": str(response.url),
            "http_status": response.status_code,
        }
        return False, f"http_{response.status_code}"

    text = _normalize_text(text)[:MAX_CONTENT_CHARS]
    if len(text) < MIN_CONTENT_CHARS:
        item.provenance = {
            "status": "insufficient_content",
            "content_url": content_url,
            "final_url": final_url,
            "http_status": response.status_code,
            "content_chars": len(text),
        }
        return False, "insufficient_content"

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    source_version = _source_version(item, etag, last_modified, content_hash)
    metadata = {
        "status": "verified",
        "content_url": content_url,
        "final_url": final_url,
        "http_status": 200 if response.status_code == 304 else response.status_code,
        "content_type": content_type,
        "content_chars": len(text),
        "content_sha256": content_hash,
        "etag": etag,
        "last_modified": last_modified,
        "cache_state": cache_state,
        "retrieved_at": retrieved_at.isoformat(),
    }
    item.content = text
    item.source_version = source_version
    item.retrieved_at = retrieved_at
    item.provenance = metadata
    _write_cache(meta_path, text_path, {**metadata, "source_version": source_version}, text)
    return True, "verified"


def _content_url(item: Item) -> str:
    external = item.raw_metrics.get("external_url")
    return str(external or item.url)


def _extract_text(response: httpx.Response, content_type: str) -> str:
    if content_type in {"application/json", "application/ld+json"}:
        try:
            return json.dumps(response.json(), ensure_ascii=False, indent=2)
        except ValueError:
            return response.text
    if content_type.startswith("text/") and content_type not in {"text/html", "text/xhtml"}:
        return response.text
    if content_type and "html" not in content_type:
        return ""

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup.select(
        "script,style,noscript,svg,nav,footer,header,form,aside,[aria-hidden='true'],"
        ".cookie,.cookies,.cookie-banner,.advertisement,.sidebar"
    ):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    body = root.get_text("\n", strip=True)
    return f"{title}\n{body}" if title and title not in body[:300] else body


def _normalize_text(text: str) -> str:
    lines = []
    for line in text.replace("\r", "\n").split("\n"):
        line = re.sub(r"[\t \u00a0]+", " ", line).strip()
        if line and (not lines or line != lines[-1]):
            lines.append(line)
    return "\n".join(lines)


def _source_version(
    item: Item,
    etag: object,
    last_modified: object,
    content_hash: str,
) -> str:
    metrics = item.raw_metrics
    if metrics.get("tag"):
        return f"release:{metrics['tag']}"
    if metrics.get("sha"):
        return f"commit:{metrics['sha']}"
    if metrics.get("arxiv_id"):
        return f"arxiv:{metrics['arxiv_id']}"
    if metrics.get("pushed_at"):
        return f"repo-push:{metrics['pushed_at']}"
    if metrics.get("entry_updated_at"):
        return f"entry-updated:{metrics['entry_updated_at']}"
    if etag:
        return f"etag:{str(etag).strip()}"
    if last_modified:
        return f"last-modified:{last_modified}"
    if item.published_at:
        return f"published:{item.published_at.isoformat()}"
    return f"sha256:{content_hash[:16]}"


def _load_cache(meta_path: Path, text_path: Path) -> tuple[dict, str] | None:
    if not meta_path.exists() or not text_path.exists():
        return None
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        text = text_path.read_text(encoding="utf-8")
        return metadata, text
    except (OSError, ValueError):
        return None


def _write_cache(meta_path: Path, text_path: Path, metadata: dict, text: str) -> None:
    try:
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        text_path.write_text(text, encoding="utf-8")
    except OSError as exc:
        log.warning("content cache write failed for %s: %s", metadata.get("content_url"), exc)
