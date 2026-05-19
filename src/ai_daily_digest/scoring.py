"""Item importance scoring.

The HTML view sorts each category by score descending; the wiki preserves this
order. Score is a float — higher = more important.

------------------------------------------------------------------------------
USER DECISION POINT — please fill in `score_item` below.
------------------------------------------------------------------------------

Each Item carries `raw_metrics` populated by its source:
  arxiv:           {"arxiv_id": "..."}
  ai_news:         {"points": int, "num_comments": int, "hn_id": ...}
  github_trending: {"stars": int, "forks": int, "language": str, "topics": list}
  llm_updates:     {"points": int, "matched_keyword": str}
  claude_code:     {"tag": "...", "is_prerelease": bool}  OR  {"sha": "..."}

Trade-offs to consider:

  - GitHub stars can be 10000+ while HN points cap around 1500. If you naively
    sum them, GitHub will always win. Normalize per-category, OR use log scale,
    OR have a category-specific weight.

  - "Importance" is subjective. A 2000-point HN post about a politics-adjacent
    AI story is high engagement but may not be useful to you. Consider keyword
    boosts (e.g. +50 for "Claude" or "Anthropic" if you work with them).

  - Items without metrics (arxiv, some claude_code) need a fallback. Otherwise
    they all score 0 and sort randomly.

  - Recency: newer items more relevant. Consider a time-decay multiplier.

Aim for 5-10 lines. You can iterate after seeing the first digest.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from .models import Item


# Calibration: HN 1000 points ≈ GitHub 10k stars ≈ score 100.
#   log1p(1000) * 14.5 = 100.2
#   log1p(10000) * 11  = 101.3
# These constants make the two scales visually comparable in the same view.
_HN_COEF = 14.5
_GH_COEF = 11.0

# Org/lab mentions that boost arXiv papers — a proxy for "likely-impactful"
# without maintaining an author whitelist.
_BIG_LABS = (
    "anthropic", "openai", "deepmind", "google research", "google deepmind",
    "meta ai", "fair ", "microsoft research", "nvidia research",
    "stanford", "mit ", "berkeley",
)

# Phrases indicating empirical results (vs pure theory pre-prints).
# Light boost — we *don't* boost hype words; the LLM summary will flag those.
_RESULT_TERMS = ("state-of-the-art", "outperform", "achieves", "surpass", "sota")


def score_item(item: Item) -> float:
    """Return importance score; HTML & wiki sort by this descending."""
    m = item.raw_metrics
    base = 0.0

    if "points" in m:                       # HN-backed sources (ai_news, llm_updates)
        base = math.log1p(m["points"]) * _HN_COEF
        base += min(m.get("num_comments", 0), 200) * 0.05  # cap discussion bonus

    elif "stars" in m:                      # github_trending
        # Prefer growth signal (new_stars per week) over cumulative — a freshly
        # exploding project with 1k new stars beats TensorFlow's 195k total.
        new_stars = m.get("new_stars", 0)
        if new_stars > 0:
            base = math.log1p(new_stars) * 20      # 1k new/wk → ~138
            base += math.log1p(m["stars"]) * 3     # cumulative as tie-breaker
        else:
            # Fallback when source didn't provide new_stars (e.g. legacy API path).
            base = math.log1p(m["stars"]) * _GH_COEF
            base += math.log1p(m.get("forks", 0)) * 1.5

    elif item.category == "arxiv":
        base = 30.0                         # baseline for any paper that surfaced
        text = f"{item.title} {item.summary or ''}".lower()
        if any(lab in text for lab in _BIG_LABS):
            base += 15
        if any(kw in text for kw in _RESULT_TERMS):
            base += 8

    elif item.category == "claude_code":
        if "tag" in m:                      # official release → high signal
            base = 100.0
            if m.get("is_prerelease"):
                base *= 0.6
        else:                               # commits → low signal floor + selective boost
            base = 5.0
            title = item.title.lower()
            if "feat:" in title or "breaking" in title:
                base += 20
            elif "fix:" in title:
                base += 4

    # Time decay: items <24h fresh get a boost, items >72h get penalized.
    if item.published_at:
        age_h = _age_hours(item.published_at)
        if age_h is not None:
            base *= max(0.3, 1.5 - age_h / 48)

    return round(base, 2)


def _age_hours(dt: datetime) -> float | None:
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return delta.total_seconds() / 3600
    except Exception:
        return None
