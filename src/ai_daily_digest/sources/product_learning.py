"""AI product manager learning sources.

These sources are intentionally not news feeds. The first three digest
categories are curriculum tracks for a junior AI PM, so every item here should
be an evergreen learning card rather than a recent discussion or headline.
"""
from __future__ import annotations

import time

from ..models import Item

TRACKS = {
    "pm_practice": {
        "source": "AI PM Curriculum",
        "cards": [
            (
                "AI 产品经理的第一性问题：用户任务、模型能力、业务闭环",
                "https://www.intercom.com/blog/designing-ai-products/",
                "学习如何从用户任务出发拆 AI 产品，而不是从模型能力出发堆功能。重点看：用户在什么场景需要 AI、AI 输出如何进入业务闭环、失败时谁兜底。",
            ),
            (
                "AI 产品需求文档：把 PRD 拆成输入、处理、输出、反馈、兜底",
                "https://www.nngroup.com/articles/ai-paradigm/",
                "AI PRD 不能只写页面和按钮，还要写清楚用户输入、模型处理链路、输出质量标准、用户反馈入口、失败兜底和人工介入。",
            ),
            (
                "Human-in-the-loop：什么时候必须让人审、改、确认",
                "https://pair.withgoogle.com/chapter/errors-failures/",
                "学习把 AI 失败当成产品流程的一部分：高风险场景要有人审核，低风险场景可以自动化，但必须让用户知道如何纠错。",
            ),
            (
                "AI 产品的核心指标：采用率、任务完成率、采纳率、纠错率",
                "https://www.nngroup.com/articles/ai-user-experience/",
                "学习 AI 产品指标不要只看 DAU 或调用量，还要看用户是否采纳 AI 建议、是否完成任务、是否频繁修改或放弃输出。",
            ),
            (
                "从 Copilot 类产品学习：AI 是副驾驶，不是替用户负责的人",
                "https://github.blog/ai-and-ml/github-copilot/",
                "学习副驾驶产品的责任边界：AI 提供草稿、建议、自动补全，但最终确认、责任和上下文判断仍由用户完成。",
            ),
            (
                "AI Agent 产品需求：目标、工具、权限、记忆、终止条件",
                "https://www.anthropic.com/engineering/building-effective-agents",
                "学习 Agent PRD 必须写清：它能调用哪些工具、权限边界是什么、什么时候停止、失败后怎么恢复、如何让用户看懂过程。",
            ),
        ],
    },
    "model_limits": {
        "source": "Model Boundary Curriculum",
        "cards": [
            (
                "大模型边界 1：幻觉不是 bug，而是概率生成的默认风险",
                "https://www.anthropic.com/research/mapping-mind-language-model",
                "学习为什么模型会给出看似合理但不可靠的答案；产品上必须设计引用、校验、低置信度提示和人工复核。",
            ),
            (
                "大模型边界 2：Prompt Injection 会让外部内容变成恶意指令",
                "https://simonwillison.net/2023/May/2/prompt-injection-explained/",
                "学习 RAG、网页总结、邮箱助手等产品为什么容易被外部文本劫持；产品需求里要写清隔离、权限和敏感操作确认。",
            ),
            (
                "大模型边界 3：上下文窗口不是长期记忆",
                "https://www.anthropic.com/news/contextual-retrieval",
                "学习长上下文、RAG、记忆是三件不同的事；产品上要区分临时上下文、可检索知识库和用户长期偏好。",
            ),
            (
                "大模型边界 4：模型能力会随任务表达方式剧烈波动",
                "https://platform.openai.com/docs/guides/prompt-engineering",
                "学习同一个模型在不同指令、样例、上下文下表现不同；产品经理要把 prompt、示例和流程当成产品规格的一部分。",
            ),
            (
                "大模型边界 5：安全、合规和品牌语气都是产品边界",
                "https://www.anthropic.com/news/constitutional-ai-harmlessness-from-ai-feedback",
                "学习模型不只是能不能答，还涉及该不该答、如何拒答、用什么语气拒答；这些都需要产品策略定义。",
            ),
        ],
    },
    "ai_evals": {
        "source": "AI Eval Curriculum",
        "cards": [
            (
                "AI 评测入门：先定义任务成功，再选择指标",
                "https://platform.openai.com/docs/guides/evals",
                "学习评测不是问模型好不好，而是验证它在具体用户任务上是否达标：准确性、完整性、格式、速度、成本和安全都可能是指标。",
            ),
            (
                "离线评测 vs 在线 A/B：一个管上线前，一个管真实用户",
                "https://www.anthropic.com/news/evaluation-reports",
                "学习离线 eval 用固定题集快速回归，在线 A/B 看真实用户行为；两者都需要，不能互相替代。",
            ),
            (
                "用 LLM-as-judge 要小心：裁判模型也会偏",
                "https://openai.com/index/evals/",
                "学习自动评审能提效，但必须抽样人工复核；要关注裁判偏见、一致性、评分标准和被测模型投机。",
            ),
            (
                "AI 产品上线门槛：红线样例、黄金集、回归集",
                "https://github.com/openai/evals",
                "学习为产品维护三类样本：绝不能错的红线、代表核心体验的黄金集、每次改 prompt/模型都要跑的回归集。",
            ),
            (
                "评测要覆盖失败：幻觉、拒答、越权、泄露、格式错、工具错",
                "https://www.nist.gov/itl/ai-risk-management-framework",
                "学习 AI PM 不能只看成功案例 demo，还要系统收集失败类型，并把失败率和兜底方案写进上线标准。",
            ),
        ],
    },
}


def fetch_pm_practice(limit: int = 30) -> list[Item]:
    return _fetch_track("pm_practice", limit)


def fetch_model_limits(limit: int = 30) -> list[Item]:
    return _fetch_track("model_limits", limit)


def fetch_ai_evals(limit: int = 30) -> list[Item]:
    return _fetch_track("ai_evals", limit)


def _fetch_track(category: str, limit: int) -> list[Item]:
    cfg = TRACKS[category]
    items = _curriculum_cards(category, cfg, max(1, min(limit, len(cfg["cards"]))))

    seen, unique = set(), []
    for it in items:
        if it.url in seen:
            continue
        seen.add(it.url)
        unique.append(it)
    return unique[:limit]


def _curriculum_cards(category: str, cfg: dict, count: int) -> list[Item]:
    cards = cfg["cards"]
    # Rotate the starting point by date so a fresh install does not always begin
    # with exactly the same card set, while dedupe still prevents repeats.
    start = int(time.time() // 86400) % len(cards)
    ordered = cards[start:] + cards[:start]
    out = []
    for idx, (title, url, summary) in enumerate(ordered[:count], start=1):
        out.append(
            Item(
                category=category,
                title=title,
                url=url,
                source=cfg["source"],
                summary=summary,
                raw_metrics={
                    "learning_card": True,
                    "curriculum_rank": idx,
                    "points": 80,
                },
            )
        )
    return out
