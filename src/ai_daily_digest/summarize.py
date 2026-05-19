"""LLM summarization via Anthropic API.

Only top-K items per category get an LLM summary (cost control).
The remaining items still appear in the HTML/wiki with their raw title+URL.

------------------------------------------------------------------------------
USER DECISION POINT — please customize `SUMMARY_PROMPT` below.
------------------------------------------------------------------------------

This prompt determines whether your daily digest reads like noise or signal.
Trade-offs:

  - Length: short (1 sentence) = scannable, but loses nuance.
            long (3-5 sentences) = informative, but you stop reading.
  - Audience: are you a researcher (want methodology, novelty claims) or
              an engineer (want what changed, how to use it)?
  - Language: Chinese for personal reading? English for keyword-searchability
              in wiki? Bilingual?
  - Skepticism: ask LLM to flag hype words ("revolutionary", "breakthrough")?

The placeholder below is generic — replace with what you actually want to read
every morning.
"""
from __future__ import annotations

import logging
import os
from typing import Iterable

from .models import Item, CATEGORY_LABELS

log = logging.getLogger(__name__)

SUMMARY_PROMPT = """请用中文为下面的 AI 领域条目写一段「深读级摘要」，严格按 3 段结构输出。

分类: {category_label}
标题: {title}
来源: {source}
原始描述: {raw}

输出格式（每段独立成行，前面带圆圈编号）：

① **事实**：发生了什么 / 提出了什么。一句话，直接陈述。不要用"这篇文章讨论了..."这类填充。不要重复标题已经说过的内容。

② **研究者视角**：关键方法、技术贡献、与已有工作的差异、关键数据指标。如果是论文/技术发布，说清楚 *novelty 在哪*；如果是工具发布，说清楚 *架构或技术路线*。一到两句。

③ **工程师视角**：怎么用、谁会受益、对生产实践的影响、是否值得切换/集成。如果是论文，说清楚 *能否落地、需要什么条件*；如果是工具，说清楚 *和现有方案的对比成本*。一到两句。

附加规则：
- 如果原文含"革命性"、"突破性"、"颠覆"、"史无前例"、"震撼"、"碾压"等夸张词，**在末尾另起一行**用 `⚠️ [hype: <疑似营销措辞>]` 标注（精简到 1 行内）。如果原文没有这类词，**不要输出 hype 行**。
- 信息不足（如只有标题、无摘要）时，宁可某一段写 "信息有限，需读原文" 也不要编造。
- 不输出任何免责声明、元注释、或"以下是摘要"之类的前言，直接给三段内容。
"""


def summarize_items(items: Iterable[Item], top_k_per_category: int = 5) -> None:
    """Mutates items in place, setting `llm_summary` on top-K per category."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log.warning("ANTHROPIC_API_KEY not set; skipping LLM summaries")
        return

    try:
        import anthropic  # lazy import — optional dep
    except ImportError:
        log.warning("anthropic package not installed; run `uv add anthropic`")
        return

    client = anthropic.Anthropic(api_key=api_key)

    # group by category, take top_k each
    by_cat: dict[str, list[Item]] = {}
    for it in items:
        by_cat.setdefault(it.category, []).append(it)
    targets: list[Item] = []
    for cat, lst in by_cat.items():
        lst.sort(key=lambda i: i.score, reverse=True)
        targets.extend(lst[:top_k_per_category])

    for it in targets:
        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                messages=[
                    {
                        "role": "user",
                        "content": SUMMARY_PROMPT.format(
                            category_label=CATEGORY_LABELS.get(it.category, it.category),
                            title=it.title,
                            source=it.source,
                            raw=(it.summary or "")[:800],
                        ),
                    }
                ],
            )
            it.llm_summary = msg.content[0].text.strip()
        except Exception as e:
            log.warning("summary failed for %r: %s", it.title[:50], e)
