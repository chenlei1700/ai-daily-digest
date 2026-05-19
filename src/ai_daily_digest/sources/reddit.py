"""Reddit — scrape old.reddit.com with 3-tier fallback.

Tier 1: anon HTML scraping (50-70% success — Reddit's anti-bot is probabilistic)
Tier 2: cookies auto-extracted from user's browser via browser_cookie3
Tier 3: report login_required so the HTML can prompt the user

The module exposes a module-level `LAST_STATUS` after each fetch_all() call so
the orchestrator (main.py) can decide whether to embed a "please login" banner
in the rendered HTML.

Routing: each subreddit's posts land in a specific category.

  r/LocalLLaMA       → llm_updates
  r/ClaudeAI         → claude_code
  r/MachineLearning  → ai_news
  r/singularity      → ai_news
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from ..models import Item

COOKIE_FILE = Path(__file__).resolve().parents[3] / "data" / "reddit_cookie.txt"
DISABLED_FILE = Path(__file__).resolve().parents[3] / "data" / "reddit_disabled"

log = logging.getLogger(__name__)

SUBREDDIT_TO_CATEGORY: dict[str, str] = {
    "LocalLLaMA": "llm_updates",
    "ClaudeAI": "claude_code",
    "MachineLearning": "ai_news",
    "singularity": "ai_news",
}

BASE = "https://old.reddit.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
}

MIN_SCORE = 30

# After each fetch_all(), one of:
#   "ok_anon"         — got data via anonymous scrape (best case)
#   "ok_browser"      — anon failed; cookies from user's browser worked
#   "login_required"  — anon failed AND browser has no Reddit cookies
#   "fetch_error"     — network / parse error unrelated to auth
LAST_STATUS: str = "unknown"


def fetch_all(limit_per_subreddit: int = 15, period: str = "day") -> list[Item]:
    global LAST_STATUS

    # ─── Persistent disable: skip Reddit entirely until sentinel file is removed.
    # Useful when Reddit's anti-bot temporarily IP-bans the user, or when the
    # user simply doesn't want Reddit data for a while. To re-enable: delete
    # `data/reddit_disabled`.
    if DISABLED_FILE.exists():
        log.info("reddit: disabled by %s; skipping (delete the file to re-enable)",
                 DISABLED_FILE.name)
        LAST_STATUS = "disabled"
        return []

    combo = "+".join(SUBREDDIT_TO_CATEGORY.keys())
    url = f"{BASE}/r/{combo}/top/"
    params = {"t": period, "limit": 100}

    # ─── Tier 0a: file cookie at data/reddit_cookie.txt (highest priority) ───
    # Best for Chrome/Edge users whose cookies are locked behind ABE — paste
    # full Cookie header into the file, no setx length limit, no Claude Code
    # restart needed (re-read on every run).
    file_cookies = _load_file_cookie()
    if file_cookies:
        parsed = _try_fetch(url, params, cookies=file_cookies, label="file-cookie")
        if parsed is not None:
            LAST_STATUS = "ok_file_cookie"
            return _balance(parsed, limit_per_subreddit)
        log.warning("reddit: file cookie present but request failed — "
                    "cookie likely expired, re-copy from browser into %s", COOKIE_FILE)
        LAST_STATUS = "cookie_expired"
        return []

    # ─── Tier 0b: env-var cookie ───
    env_cookies = _parse_env_cookie()
    if env_cookies:
        parsed = _try_fetch(url, params, cookies=env_cookies, label="env-var")
        if parsed is not None:
            LAST_STATUS = "ok_env_cookie"
            return _balance(parsed, limit_per_subreddit)
        log.warning("reddit: REDDIT_COOKIE is set but request still failed "
                    "(cookie may be expired — re-copy from browser)")

    # ─── Tier 1: anon attempt (with cookie warm-up + one retry) ───
    parsed = _try_fetch(url, params, cookies=None, label="anon")
    if parsed is not None:
        LAST_STATUS = "ok_anon"
        return _balance(parsed, limit_per_subreddit)

    # ─── Tier 2: browser cookie fallback ───
    browser_cookies = _load_browser_cookies()
    if browser_cookies is None:
        # No browser cookies found AT ALL — user hasn't logged in to Reddit.
        log.warning("reddit: anon failed and no browser cookies for reddit.com found. "
                    "Please log in to https://reddit.com in your browser, then re-trigger.")
        LAST_STATUS = "login_required"
        return []

    parsed = _try_fetch(url, params, cookies=browser_cookies, label="browser-cookie")
    if parsed is not None:
        LAST_STATUS = "ok_browser"
        return _balance(parsed, limit_per_subreddit)

    # Cookies exist but Reddit still rejected — likely expired session.
    log.warning("reddit: browser cookies present but still blocked. Cookies likely expired — "
                "please log in to https://reddit.com again in your browser, then re-trigger.")
    LAST_STATUS = "login_required"
    return []


def _try_fetch(url, params, cookies, label: str) -> list[Item] | None:
    """Returns parsed items list, or None on failure. Never raises."""
    try:
        with httpx.Client(
            timeout=20.0, headers=HEADERS, follow_redirects=True, cookies=cookies
        ) as client:
            # Warm-up: visit homepage so the listing page sees us as a returning
            # visitor. For anon this also plants session_tracker cookie.
            try:
                client.get(f"{BASE}/", timeout=10.0)
            except Exception:
                pass

            for attempt in (1, 2):
                r = client.get(url, params=params)
                if r.status_code == 200:
                    log.info("reddit [%s] OK on attempt %d", label, attempt)
                    return _parse_listing(r.text)
                if r.status_code == 403 and attempt == 1:
                    log.info("reddit [%s] 403; waiting 15s and retrying", label)
                    time.sleep(15)
                    continue
                log.info("reddit [%s] failed: status %d", label, r.status_code)
                return None
    except Exception as e:
        log.info("reddit [%s] error: %s", label, e)
        return None
    return None


def _load_file_cookie() -> dict[str, str] | None:
    """Read cookies from `data/reddit_cookie.txt`.

    Accepted formats (auto-detected):
      - Single line, Cookie header style: `name1=val1; name2=val2; ...`
      - One `name=value` per line (semicolons or newlines both work)
    """
    if not COOKIE_FILE.exists():
        return None
    try:
        raw = COOKIE_FILE.read_text(encoding="utf-8").strip()
    except Exception as e:
        log.warning("reddit: failed to read %s: %s", COOKIE_FILE, e)
        return None
    if not raw:
        return None
    # Normalize separators
    raw = raw.replace("\n", ";")
    cookies: dict[str, str] = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    if cookies:
        log.info("reddit: loaded %d cookies from data/reddit_cookie.txt (keys=%s)",
                 len(cookies), list(cookies.keys())[:6])
    return cookies or None


def _parse_env_cookie() -> dict[str, str] | None:
    """Parse `REDDIT_COOKIE` env var.

    Accepts either:
      - raw Cookie header: `name1=val1; name2=val2; ...`
      - single token: `<your_session_value>` (we assume it's `reddit_session`)
    """
    raw = os.getenv("REDDIT_COOKIE", "").strip()
    if not raw:
        return None
    if "=" not in raw:
        # Treat as a single token assumed to be reddit_session
        return {"reddit_session": raw}
    cookies: dict[str, str] = {}
    for part in raw.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    log.info("reddit: using REDDIT_COOKIE from env (%d cookies, keys=%s)",
             len(cookies), list(cookies.keys())[:5])
    return cookies or None


def _load_browser_cookies():
    """Try each installed browser for reddit.com cookies; return first match.

    Returns an httpx-compatible cookie dict, or None if nothing found.

    Order: firefox / edge / brave / chromium / opera / chrome — Chrome 122+ uses
    App-Bound Encryption on Windows which often requires admin to decrypt, so
    we try it last. Firefox is the most reliable on Windows.
    """
    try:
        import browser_cookie3
    except ImportError:
        log.warning("browser_cookie3 not installed; cannot do cookie fallback")
        return None

    for browser in ("firefox", "edge", "brave", "chromium", "opera", "librewolf", "chrome"):
        getter = getattr(browser_cookie3, browser, None)
        if not getter:
            continue
        try:
            cj = getter(domain_name="reddit.com")
            cookies = {c.name: c.value for c in cj if "reddit.com" in (c.domain or "")}
            if cookies:
                log.info("reddit: loaded %d cookies from %s (keys: %s)",
                         len(cookies), browser, list(cookies.keys())[:5])
                return cookies
            log.info("reddit: %s is installed but has no reddit.com cookies "
                     "(user hasn't logged in via this browser)", browser)
        except Exception as e:
            log.info("reddit: %s cookie read failed (%s)", browser, e)
            continue
    log.info("reddit: no browser had reddit.com cookies (you may need to log in)")
    return None


def _balance(items: list[Item], per_sub_cap: int) -> list[Item]:
    """Group by subreddit, cap each, flatten."""
    by_sub: dict[str, list[Item]] = {}
    for it in items:
        sub = it.raw_metrics.get("subreddit", "?")
        by_sub.setdefault(sub, []).append(it)
    out: list[Item] = []
    for sub, lst in by_sub.items():
        kept = lst[:per_sub_cap]
        out.extend(kept)
        log.info("  r/%s → %d posts kept", sub, len(kept))
    return out


def _parse_listing(html: str) -> list[Item]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Item] = []

    for div in soup.select('div.thing[data-fullname^="t3_"]'):
        if "promoted" in div.get("class", []) or div.get("data-promoted") == "true":
            continue

        subreddit = div.get("data-subreddit") or ""
        category = SUBREDDIT_TO_CATEGORY.get(subreddit)
        if not category:
            continue

        score = _parse_score(div.select_one(".score.unvoted"))
        if score < MIN_SCORE:
            continue

        title_a = div.select_one("a.title")
        if not title_a:
            continue
        title = title_a.get_text(strip=True)

        comments_a = div.select_one("a.comments")
        permalink = _absolutize(comments_a["href"]) if comments_a and comments_a.has_attr("href") else None
        if not permalink:
            continue

        href = title_a.get("href", "")
        external_url = _absolutize(href) if href and not href.startswith("/r/") else None

        num_comments = _parse_int(
            comments_a.get_text(" ", strip=True).split()[0] if comments_a else "0"
        )

        author_a = div.select_one(".tagline a.author")
        author = author_a.get_text(strip=True) if author_a else None

        time_el = div.select_one("time")
        published_at = _parse_time(time_el.get("datetime")) if time_el else None

        flair_el = div.select_one(".linkflairlabel")
        flair = flair_el.get_text(strip=True) if flair_el else None

        out.append(Item(
            category=category,
            title=title,
            url=permalink,
            source=f"r/{subreddit}",
            published_at=published_at,
            author=author,
            summary="",
            raw_metrics={
                "points": score,
                "num_comments": num_comments,
                "subreddit": subreddit,
                "external_url": external_url,
                "flair": flair,
            },
        ))
    return out


def _parse_score(el) -> int:
    if el is None:
        return 0
    txt = el.get_text(strip=True).replace(",", "")
    if txt.endswith("k"):
        try:
            return int(float(txt[:-1]) * 1000)
        except ValueError:
            return 0
    return int(txt) if txt.isdigit() else 0


def _parse_int(s: str) -> int:
    s = re.sub(r"[^\d]", "", s)
    return int(s) if s else 0


def _absolutize(href: str) -> str:
    if href.startswith("/"):
        return "https://www.reddit.com" + href
    return href


def _parse_time(iso: str | None):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None
