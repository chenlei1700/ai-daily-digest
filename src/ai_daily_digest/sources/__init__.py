"""Data source modules.

Two kinds of fetchers:
  - `FETCHERS` (category → fetch(limit)): single-category sources
  - `MULTI_CATEGORY_FETCHERS`: produce items across multiple categories in one call.
"""
from . import (
    arxiv,
    ai_news,
    github_trending,
    llm_updates,
    claude_code,
    codex,
    product_learning,
    reddit,
)

FETCHERS = {
    "pm_practice": product_learning.fetch_pm_practice,
    "model_limits": product_learning.fetch_model_limits,
    "ai_evals": product_learning.fetch_ai_evals,
    "arxiv": arxiv.fetch,
    "ai_news": ai_news.fetch,
    "github_trending": github_trending.fetch,
    "llm_updates": llm_updates.fetch,
    "claude_code": claude_code.fetch,
    "codex": codex.fetch,
}

MULTI_CATEGORY_FETCHERS = [reddit.fetch_all]
