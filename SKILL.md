---
name: ai-daily-digest
description: Collect daily AI-domain updates and AI product-manager learning materials across 9 categories (AI product practice, model limits, AI evals, papers, news, GitHub trending, LLM updates, Claude Code, Codex), deduplicate against prior days, rank by learning value, write product-manager-oriented summaries yourself (no API call), render a tabbed HTML brief, and open it in the browser. Use when the user says "AI 日报"、"AI 产品经理日报"、"今日 AI 简报"、"今天 AI 圈"、"daily ai digest"、"ai daily news"、"跑一下日报"、"看下今日 AI"、or similar.
---

# AI Daily Digest — skill-mode runner

## How this skill works (read first)

This skill is split into **two Python stages** with **you (Claude) in the middle**:

```
[ Python: collect ]  →  pending.json  →  [ you: summarize (并发) ]  →  summaries.json  →  [ Python: apply ]  →  HTML
```

You don't need an API key. The Python side does no LLM call — **you write the summaries yourself** by reading `pending.json` and saving `summaries.json`.

**性能要点**：当 `pending.items ≥ 20` 时**必须**用 `Agent` 工具并发处理（按 category 分组 spawn 多个 subagent 同时写），否则 100+ 条摘要的串行生成会耗时 40+ 分钟。详见 Step 4e。

## Auto-execution flow

When the user invokes this skill, execute steps 1-6 in order. Stop and report if any step fails.

### Step 1 — Locate the skill root

Skill root: the directory containing this `SKILL.md`. `cd` into it before running any commands.

### Step 2 — Check whether today's digest already exists

If `output/digest-<today>.html` exists and was modified within the last 30 minutes, **skip to Step 6** (just re-open it). Tell the user: *"已使用 N 分钟前的简报。"*

### Step 3 — Check GitHub CLI (first-run only)

If `gh` is not installed or not logged in, GitHub-backed sources can be sparse due to API limits. Claude Code releases have Atom/npm fallbacks, but authenticated GitHub is still more complete. Check once per session:

```bash
if ! command -v gh >/dev/null 2>&1 || ! gh auth status >/dev/null 2>&1; then
    echo "⚠️  GitHub CLI not found or not logged in."
    echo "GitHub-backed sources may be sparse without it."
    echo "Install: brew install gh && gh auth login"
fi
```

If the check fails, **tell the user** (don't silently proceed). Most users can fix this in 2 minutes.

### Step 4 — Run the `collect` stage

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

**⚡ 性能要求（重要）**：当 `pending.items` ≥ 20 条时，**必须并发处理**。串行写 100+ 条摘要会让整个流程从 ~5 分钟延长到 40+ 分钟。具体做法见 **4e**。

**4a.** Read `output/digest-YYYY-MM-DD.pending.json`. Each item has:

```json
{
  "url": "...",
  "category": "pm_practice",
  "category_label": "AI 产品方法",
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

你要把摘要写给一个**零基础 AI 产品经理实习生**，目标不是炫技，而是帮她建立可复用的产品判断框架。写四段，每段独立成行，前面带圆圈编号：

> ① **发生了什么**：用一句人话说明这条内容讲什么，避免术语堆砌。
>
> ② **你要学的概念**：解释 1 个关键 AI 产品概念，例如模型边界、幻觉、RAG、评测集、A/B、人工兜底、Agent 权限、输入输出约束等。
>
> ③ **产品经理怎么用**：落到需求梳理、用户场景、PRD、指标、上线门槛、失败兜底、风险提示或商业化判断。
>
> ④ **可以追问的问题**：给 1-2 个具体问题，帮助她继续学习或在需求评审中提问。

分类侧重点：
- `pm_practice`：重点讲需求拆解、用户任务、流程设计、指标、PRD 写法。
- `model_limits`：重点讲大模型能力边界、失败模式、风险和兜底方案。
- `ai_evals`：重点讲怎么评测、用什么样本、什么指标、上线前怎么验收。
- `arxiv`：不要过度讲公式，重点翻译成“这个能力未来可能影响什么产品”。
- `github_trending` / `claude_code` / `codex`：重点讲工具或平台变化会改变什么工作流。
- `ai_news` / `llm_updates`：重点讲行业变化对产品机会、风险、竞品判断的影响。

如果原文（title 或 raw）含"革命性"、"突破性"、"颠覆"、"史无前例"、"震撼"、"碾压"等夸张词，**在末尾另起一行**用 `⚠️ [hype: <疑似营销措辞>]` 标注。原文没这类词就**不要输出 hype 行**。

#### When `summary_mode == "brief"` (everything else)

写 **1 句中文**（30-100 字），直接说明“这对 AI 产品经理学习有什么用”。**不要分段、不要圆圈编号**。如果信息有限，按上面 common rules 处理。

**4c.** Output schema — `{url: {title_zh, summary}}`:

```json
{
  "https://www.nngroup.com/articles/ai-user-experience/": {
    "title_zh": "AI 产品指标：看任务完成而不是只看调用量",
    "summary": "① 发生了什么：这篇内容提醒 AI 产品不能只用访问量或调用量判断成功。\n② 你要学的概念：AI 产品的核心指标应围绕任务完成、采纳率、纠错率和失败兜底，而不是模型看起来多聪明。\n③ 产品经理怎么用：写 PRD 时要把“用户是否采纳 AI 输出”“输出错了怎么改”“哪些场景必须人工确认”写成验收标准。\n④ 可以追问的问题：这个功能的成功样本和失败样本各是什么？上线前最低可接受的错误率是多少？"
  },
  "https://github.com/openclaw/openclaw": {
    "title_zh": "openclaw/openclaw：跨平台个人 AI 助手项目（一周冲上 ★373k）",
    "summary": "本周 GitHub trending 冠军，定位 \"any OS, any platform\" 的个人 AI 助手；具体技术栈与质量需查 README 评估。"
  }
}
```

**4d.** Use the **Write tool** to save to `output/digest-YYYY-MM-DD.summaries.json` (UTF-8).

**IMPORTANT — don't dump summaries to chat.** Write the file silently. The user sees them in HTML, not in chat. Echoing 70 summaries floods the conversation.

**⚠️ 大文件分段写入（必须遵守，避免 launchd 卡死）**：单次响应输出上限为 8192 tokens，~80 条摘要的 JSON 通常 > 50KB，**直接 Write 会触发"文件过大"提示并卡住后台执行**。正确做法：

1. **先建空骨架**：用 Write 写入 `{}` 或 `{"<first_url>": {...}}` 创建文件
2. **再用 Edit 追加**：每次 Edit 追加 ~10-15 条（每条约 500 字节），通过精确匹配 `"summary": "..."\n  }\n}` 形式的尾部锚点插入新条目
3. **绝不询问用户**：在任何环境下（交互/后台/launchd）遇到"是否分段写入"的提示时，**直接选择分段写入并继续执行**，不要等待确认
4. **简化策略**：如果觉得 Edit 追加复杂，可以直接把摘要分成多批，每批一个 Write 写到 `summaries.part1.json`、`summaries.part2.json`，最后用 `python -c "import json; ..."` 一行命令合并成 `summaries.json`

**4e. 并发执行规范（pending.items ≥ 20 时必须采用）**

串行生成 102 条摘要的实测耗时约 42 分钟（2026-06-03 实例），并发后可压到 6-8 分钟。流程：

1. **按 category 分组**：把 `pending.items` 按 `category` 字段分桶。常见分桶：`pm_practice`、`model_limits`、`ai_evals`、`arxiv`、`ai_news`、`github_trending`、`llm_updates`、`claude_code`、`codex`。
2. **大桶再切片**：单个 category 超过 20 条时，按 `score` 降序均分成 ~15 条/片的子任务，避免单个 subagent 输出过长被截断。
3. **并发 spawn subagents**：在**同一条消息**里并行调用 `Agent` 工具（`subagent_type=general-purpose`），每个 subagent 一个分组/分片。每个 subagent 的 prompt **必须自包含**（subagent 看不到本对话上下文），需要包含：
   - 该分组所有条目的完整 JSON（url / title / source / summary_mode / raw）
   - 完整的 title_zh 与 summary 规则（参见 4b、4c 整段，原文复制到 prompt 里）
   - 输出要求：**只返回 `{url: {title_zh, summary}}` 形式的 JSON，不要任何解释文字**
4. **主线程合并（分段写入，避免 launchd 卡死）**：等所有 subagent 返回后，**不要一次性 Write 大 JSON**（会触发"文件过大"询问导致后台卡死）。改用以下任一方式：
   - **方式 A（推荐）**：让每个 subagent 直接 `Write` 到独立的 `output/digest-DATE.summaries.part-<category>.json`，主线程**只**用一条 Bash 命令合并：
     ```bash
     python3 -c "import json,glob; d={}; [d.update(json.load(open(p))) for p in glob.glob('output/digest-DATE.summaries.part-*.json')]; json.dump(d, open('output/digest-DATE.summaries.json','w'), ensure_ascii=False, indent=2)"
     ```
   - **方式 B**：主线程先 Write 空 `{}`，再按分组用 Edit 逐个追加（参见 4d）。
5. **覆盖率校验**：合并后 keys 数应等于 `pending.items` 长度。少了的 url 单独补一次（在主线程直接写一条，或起一个 mini subagent）。
6. **失败重试**：如果某个 subagent 报错或返回的不是合法 JSON，对该分组重试一次；仍失败则在主线程串行处理这一组（保证总数完整）。

**⛔ 合并失败的红线（2026-07-16 事故教训，必须遵守）**：

subagent 常在 summary 正文里写**未转义的半角双引号**，拼接后 JSON 非法。这**几乎每次都会发生**，属于已知问题，**不是**放弃摘要的理由。

- **正确做法**：让每个 subagent 各自 `Write` 到独立的 `part-<category>.json`（方式 A），由 Python 的 `json.load` 逐个解析——单个文件坏了只影响一组，且 subagent 自己写文件时引号已由工具正确转义。若仍有某个 part 解析失败，**只重跑那一组**，其余已生成的摘要必须保留。
- **绝对禁止**：合并遇到任何编码/解析错误时，**不允许**跳过摘要直接跑 `apply`。那会让 `_fallback_summary` 把全部条目填成「信息有限，需读原文」占位符，等于当天日报全废（2026-07-16 就是这样，112 条全部退化）。
- **收尾自检**：`apply` 会打印 `real=N fallback=M`。**M 必须接近 0**。若 `fallback` 占比过高（apply 会用 ⚠️ ERROR 日志报出），说明摘要没接上，**必须回头修合并、重跑 apply**，不能就这么交付。

**何时不用并发**：`pending.items < 20` 时直接在主线程串行写更划算（subagent 启动 + 跨进程 IO 反而更慢）。

**禁止**：不要把整个 102 条塞进一个 subagent —— 单 agent 输出仍是串行 token 流，不会更快。并发的核心是**多个 subagent 同时跑**。

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

**macOS/Linux:**
```bash
open "<the html path>"
```

**Windows:**
```powershell
Invoke-Item "<the html path>"
```

Use the command appropriate for the current platform.

### Step 7 — Report back

Short Chinese summary (2-3 lines):

> 今日 AI 简报已生成：**N 条新内容**（去重 D 条），已为 **P 条 top items** 写入摘要。
> - AI 产品方法 X · 大模型边界 X · AI 评测 X · 重要论文 X · AI 新闻 X · GitHub 热门 X · 大模型动态 X · Claude Code X · Codex X
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
│   ├── product_learning.py  # AI PM curriculum cards
│   ├── arxiv.py, ai_news.py, github_trending.py, llm_updates.py, claude_code.py, codex.py
│   └── reddit.py      # routes subreddits → related categories
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

```bash
cd ~/.claude/skills/ai-daily-digest

# Stage 1 alone:
uv run python -m ai_daily_digest.main collect --quiet
uv run python -m ai_daily_digest.main collect --limit-per-source 20 --top-k-summary 3

# Stage 2 alone (after you've written summaries.json):
uv run python -m ai_daily_digest.main apply --quiet

# Only fetch certain categories:
uv run python -m ai_daily_digest.main collect --categories pm_practice,model_limits,ai_evals --quiet

# Override date:
uv run python -m ai_daily_digest.main collect --date 2026-05-18 --quiet
```
