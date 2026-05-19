---
name: ai-daily-digest
description: Collect daily AI-domain updates across 5 categories (papers, AI news, GitHub trending, LLM updates, Claude Code releases), deduplicate against prior days, rank by importance, write three-section summaries yourself (no API call), render a tabbed HTML brief, and open it in the browser. Use when the user says "AI 日报"、"今日 AI 简报"、"今天 AI 圈"、"daily ai digest"、"ai daily news"、"跑一下日报"、"看下今日 AI"、or similar.
---

# AI Daily Digest — skill-mode runner

## How this skill works (read first)

This skill is split into **two Python stages** with **you (Claude) in the middle**:

```
[ Python: collect ]  →  pending.json  →  [ you: summarize ]  →  summaries.json  →  [ Python: apply ]  →  HTML
```

You don't need an API key. The Python side does no LLM call — **you write the summaries yourself** by reading `pending.json` and saving `summaries.json`.

## Auto-execution flow

When the user invokes this skill, execute steps 1-6 in order. Stop and report if any step fails.

### Step 1 — Locate the skill root

Skill root: `D:\work\claude_learn\skills\ai-daily-digest\`. If the path doesn't exist, `cd` to the directory containing this `SKILL.md`.

### Step 2 — Check whether today's digest already exists

If `output/digest-<today>.html` exists and was modified within the last 30 minutes, **skip to Step 6** (just re-open it). Tell the user: *"已使用 N 分钟前的简报。"*

### Step 3 — Run the `collect` stage

```powershell
uv run python -m ai_daily_digest.main collect --quiet
```

The command prints a final marker line:

```
COLLECT_READY items=N deduped=D pending=P items_json=... pending_json=... date=YYYY-MM-DD
```

Parse this line. If `pending=0`, all items were already in the dedup store — skip to Step 5 with no summaries (apply will still render).

### Step 4 — Read `pending.json` and write `summaries.json` yourself

This is **your job, not Python's**. For **every item** in `pending.json::items[]`, produce a Chinese title translation **and** a Chinese summary (length depends on `summary_mode`).

**4a.** Read `output/digest-YYYY-MM-DD.pending.json`. Each item has:

```json
{
  "url": "...",
  "category": "arxiv",
  "category_label": "重要论文",
  "title": "<original title, usually English>",
  "source": "arXiv",
  "score": 47.2,
  "summary_mode": "deep" | "brief",
  "raw": "<original abstract / description, may be empty>"
}
```

**4b.** For every item, decide title and summary by **`summary_mode`**:

#### Common rules for `title_zh` (all items)

- Translate to natural Chinese. **Don't word-by-word transliterate**.
- **Keep product / project / model names untranslated** (e.g. `DashAttention`、`Qwen 3.7`、`tensorflow/tensorflow`). Translate only the descriptive part.
- If the original title is already Chinese, set `title_zh` to the original.
- Aim for 15-30 Chinese characters.

#### Common rules for `summary` (all items)

- 必须使用中文。
- 信息不足（如 `raw` 为空、只有标题）时，写 *"信息有限，需读原文。<可以从标题推断的一句话>"* — 不要编造细节。
- 不要"以下是摘要"之类的元注释。直接给内容。
- **不要重复标题里已说过的内容**。

#### When `summary_mode == "deep"` (top-K per category)

写三段，每段独立成行，前面带圆圈编号：

> ① **事实**：发生了什么 / 提出了什么。一句话。
>
> ② **研究者视角**：关键方法、技术贡献、与已有工作的差异、关键数据指标。一到两句。
>
> ③ **工程师视角**：怎么用、谁会受益、对生产实践的影响、是否值得切换 / 集成。一到两句。

如果原文（title 或 raw）含"革命性"、"突破性"、"颠覆"、"史无前例"、"震撼"、"碾压"等夸张词，**在末尾另起一行**用 `⚠️ [hype: <疑似营销措辞>]` 标注。原文没这类词就**不要输出 hype 行**。

#### When `summary_mode == "brief"` (everything else)

写 **1 句中文**（30-80 字），直接概括做什么 / 值得关注的核心点。**不要分段、不要圆圈编号**。如果信息有限，按上面 common rules 处理。

**4c.** Output schema — `{url: {title_zh, summary}}`:

```json
{
  "https://arxiv.org/abs/2605.18753v1": {
    "title_zh": "DashAttention：可微的自适应稀疏分层注意力",
    "summary": "① 事实：提出端到端可微的稀疏分层注意力 DashAttention。\n② 研究者视角：用 α-entmax 自适应选块，保留稀疏-密集间梯度流，与 NSA/InfLLMv2 的硬 top-k 不同。\n③ 工程师视角：值得长上下文推理团队评估，但需重训对齐，非即插即用。"
  },
  "https://github.com/openclaw/openclaw": {
    "title_zh": "openclaw/openclaw：跨平台个人 AI 助手项目（一周冲上 ★373k）",
    "summary": "本周 GitHub trending 冠军，定位 \"any OS, any platform\" 的个人 AI 助手；具体技术栈与质量需查 README 评估。"
  }
}
```

**4d.** Use the **Write tool** to save to `output/digest-YYYY-MM-DD.summaries.json` (UTF-8).

**IMPORTANT — don't dump summaries to chat.** Write the file silently. The user sees them in HTML, not in chat. Echoing 70 summaries floods the conversation.

### Step 5 — Run the `apply` stage

```powershell
uv run python -m ai_daily_digest.main apply --quiet
```

This prints:

```
DIGEST_READY html=... wiki=... items=N deduped=D summaries_applied=P
```

Parse to get the HTML path.

### Step 6 — Open the HTML

```powershell
Invoke-Item "<the html path>"
```

### Step 7 — Report back

Short Chinese summary (2-3 lines):

> 今日 AI 简报已生成：**N 条新内容**（去重 D 条），已为 **P 条 top items** 写入摘要。
> - 重要论文 X · AI 新闻 X · GitHub 热门 X · 大模型动态 X · Claude Code X
> - 已在浏览器中打开 `digest-YYYY-MM-DD.html`；Wiki 归档：`data\wiki\YYYY-MM-DD.md`

Per-category counts come from `data/wiki/YYYY-MM-DD.md`'s `## Contents` section. **Do not invent numbers.**

## Constraints

- **Don't echo summaries in chat.** Write directly to `summaries.json`. The HTML is the user-facing artifact.
- **Don't ask the user before running.** The skill is "say-and-show".
- **Don't skip Step 4.** Even if `pending.json` has 25 items, you must summarize all of them. The HTML will look skeletal if summaries are missing.
- **Don't invent URLs or paths.** Always parse them from the `COLLECT_READY` / `DIGEST_READY` lines.

## Edge cases

- **Network/API failure during collect**: per-source failures are logged but don't abort. Empty categories show as 0 — report them as such.
- **No new items today** (`pending=0`): skip Step 4, just run `apply` (produces an HTML showing "本类今日无新内容" in each tab). Tell user this is normal — the dedup is working.
- **Re-run same day**: dedup will filter most items, so `pending` will be small. Summarize only what's there.
- **`summaries.json` already exists from a prior run**: overwrite it. The apply stage uses the latest version.

## Project layout (for reference)

```
src/ai_daily_digest/
├── main.py            # `collect` and `apply` subcommands
├── sources/           # category fetchers + reddit (multi-category)
│   ├── arxiv.py, ai_news.py, github_trending.py, llm_updates.py, claude_code.py
│   └── reddit.py      # routes 5 subreddits → 3 categories (see file)
├── models.py          # Item, CATEGORIES, CATEGORY_LABELS
├── dedupe.py          # SQLite seen-set
├── scoring.py         # importance heuristic
├── summarize.py       # OPTIONAL legacy API path (not used in skill mode)
├── render_html.py     # Jinja2 → tabbed HTML; _split_hype handles ⚠️ line
└── render_wiki.py     # markdown archive
output/
├── digest-DATE.items.json       # full snapshot from collect
├── digest-DATE.pending.json     # YOUR INPUT in Step 4
├── digest-DATE.summaries.json   # YOUR OUTPUT in Step 4
└── digest-DATE.html             # final, opened in Step 6
data/wiki/DATE.md                # markdown archive
data/seen.db                     # incremental dedup state
```

## Manual invocation (debugging only)

```powershell
cd D:\work\claude_learn\skills\ai-daily-digest

# Stage 1 alone:
uv run python -m ai_daily_digest.main collect --quiet
uv run python -m ai_daily_digest.main collect --limit-per-source 20 --top-k-summary 3

# Stage 2 alone (after you've written summaries.json):
uv run python -m ai_daily_digest.main apply --quiet

# Only fetch certain categories:
uv run python -m ai_daily_digest.main collect --categories arxiv,claude_code --quiet

# Override date:
uv run python -m ai_daily_digest.main collect --date 2026-05-18 --quiet
```
