"""Data source modules.

Two kinds of fetchers:
  - `FETCHERS` (category → fetch(limit)): single-category sources
  - `MULTI_CATEGORY_FETCHERS`: produce items across multiple categories in one call.
"""
from . import (
    arxiv, ai_news, github_trending, llm_updates, claude_code, reddit,
    intl_politics, china_news,
)

FETCHERS = {
    "arxiv": arxiv.fetch,
    "ai_news": ai_news.fetch,
    "github_trending": github_trending.fetch,
    "llm_updates": llm_updates.fetch,
    "claude_code": claude_code.fetch,
    "intl_politics": intl_politics.fetch,
    "china_news": china_news.fetch,
}

MULTI_CATEGORY_FETCHERS = [reddit.fetch_all]
