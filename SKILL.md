---
name: ai-daily-digest
description: Collect auto-updating AI-domain and AI product-manager learning materials across 9 categories, verify every public link, extract and version the actual webpage text, deduplicate and rank it, write evidence-bound Chinese summaries yourself (no API call), render a traceable HTML brief, and open it in the browser. Use when the user says "AI 日报"、"AI 产品经理日报"、"今日 AI 简报"、"今天 AI 圈"、"daily ai digest"、"ai daily news"、"跑一下日报"、"看下今日 AI"、or similar.
---

# AI Daily Digest — skill-mode runner

## How this skill works (read first)

This skill uses Python for deterministic collection, batching, validation, and
rendering, with **you (Claude) only writing the summaries**:

```
[ collect + verify + bounded slices ] → [ summary agents, max 6 at once ] → [ validate + merge ] → [ apply ] → HTML
```

You don't need an extra API key. The Python side does no LLM call — **you write
the summaries from bounded slice files**, and Python validates and merges them.

**性能要点**：`collect` 已按实际正文体量自动切片。必须读取生成的
`manifest.json`，每批最多运行其中 `recommended_parallel_agents` 个任务
（默认 6），禁止把所有分片一次性并发提交。详见 Step 5d。

## Auto-execution flow

When the user invokes this skill, execute steps 1-8 in order. Stop and report if any step fails.

### Step 1 — Locate the skill root

Skill root: the directory containing this `SKILL.md`. `cd` into it before running any commands.

### Step 2 — Check whether today's digest already exists

If `output/digest-<today>.html` exists and was modified within the last 30 minutes, **skip to Step 8** (just re-open it). Tell the user: *"已使用 N 分钟前的简报。"*

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
COLLECT_READY items=N deduped=D pending=P verified=V invalid=I slices=S max_parallel=6 items_json=... pending_json=... slices_manifest=... date=YYYY-MM-DD
```

Parse this line. `collect` has already created bounded slice files and their
manifest. If `pending=0`, all items were already in the dedup store — skip to
Step 6 with no summaries (apply will still render).

### Step 5 — Write summaries from bounded slices

This is **your job, not Python's**. For every item listed across the manifest's
slice files, produce a Chinese title translation and summary.

**⚡ 性能要求（重要）**：不要直接读取整份 `pending.json`。始终使用
`COLLECT_READY` 返回的 `slices_manifest` 和其中的小分片。具体做法见 **5d**。

**5a.** Each slice item has:

```json
{
  "url": "...",
  "category": "pm_practice",
  "category_label": "AI 产品方法",
  "title": "<original title, usually English>",
  "source": "arXiv",
  "score": 47.2,
  "summary_mode": "deep" | "brief",
  "content": {
    "text": "<text extracted from the verified public webpage>",
    "content_url": "...",
    "http_status": 200,
    "content_sha256": "...",
    "content_chars": 6000,
    "full_content_chars": 16000,
    "is_excerpt": true,
    "retrieved_at": "2026-07-20T09:00:00+00:00",
    "source_version": "etag:..."
  },
  "source_metadata": {
    "source_tier": "S" | "A" | "B" | null,
    "publisher": "...",
    "source_config_version": "..."
  }
}
```

For brief items, `is_excerpt=true` means `content.text` is a verified leading
excerpt used to control latency. `content_sha256` and `source_version` still
identify the full verified webpage. Do not fetch the page again.

**5b.** For every item, decide title and summary by **`summary_mode`**:

#### Common rules for `title_zh` (all items)

- Translate to natural Chinese. **Don't word-by-word transliterate**.
- **Keep product / project / model names untranslated** (e.g. `DashAttention`、`Qwen 3.7`、`tensorflow/tensorflow`). Translate only the descriptive part.
- If the original title is already Chinese, set `title_zh` to the original.
- Aim for 15-30 Chinese characters.

#### Common rules for `summary` (all items)

- 必须使用中文。
- **只能把 `content.text` 当作事实依据。** 标题、来源热度和你的背景知识只能帮助理解，不得补写网页中没有的事实。
- `collect` 已读取并验证网页；不要只看标题或发现接口的短描述，也不要声称“需要再读原文”。
- 如果正文确实没有支持某个细节，就省略该细节；不要推断数字、因果、发布日期或产品能力。
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

如果原文（title 或 `content.text`）含"革命性"、"突破性"、"颠覆"、"史无前例"、"震撼"、"碾压"等夸张词，**在末尾另起一行**用 `⚠️ [hype: <疑似营销措辞>]` 标注。原文没这类词就**不要输出 hype 行**。

#### When `summary_mode == "brief"` (everything else)

写 **1 句中文**（30-100 字），直接说明“网页讲了什么，以及这对 AI 产品经理学习有什么用”。**不要分段、不要圆圈编号**。

**5c.** Output schema — `{url: {title_zh, summary, content_sha256, source_version}}`。后两个字段必须从该条目的 `content` 原样复制；合并和 `apply` 都会拒绝缺失、过期或不匹配的摘要：

```json
{
  "https://www.nngroup.com/articles/ai-user-experience/": {
    "title_zh": "AI 产品指标：看任务完成而不是只看调用量",
    "summary": "① 发生了什么：这篇内容提醒 AI 产品不能只用访问量或调用量判断成功。\n② 你要学的概念：AI 产品的核心指标应围绕任务完成、采纳率、纠错率和失败兜底，而不是模型看起来多聪明。\n③ 产品经理怎么用：写 PRD 时要把“用户是否采纳 AI 输出”“输出错了怎么改”“哪些场景必须人工确认”写成验收标准。\n④ 可以追问的问题：这个功能的成功样本和失败样本各是什么？上线前最低可接受的错误率是多少？",
    "content_sha256": "<copy from content.content_sha256>",
    "source_version": "<copy from content.source_version>"
  },
  "https://github.com/openclaw/openclaw": {
    "title_zh": "openclaw/openclaw：跨平台个人 AI 助手项目（一周冲上 ★373k）",
    "summary": "网页将其定位为跨平台个人 AI 助手；产品经理可据正文继续评估它减少了哪些操作，以及权限和可靠性风险。",
    "content_sha256": "<copy from content.content_sha256>",
    "source_version": "<copy from content.source_version>"
  }
}
```

**5d. Bounded concurrent execution (mandatory)**

Read `slices_manifest`. It contains the exact `input_path`, `output_path`, item
count, input size, and URL list for every slice. Python has already grouped by
category and enforced both a 40,000-character input budget and an 8-item cap.
Do not create different slices yourself.

1. If `slice_count == 1` and `total_items < 20`, process that slice in the main
   thread using `references/summary-agent.md` and then continue to Step 6.
2. Otherwise, process slices in waves. Each wave may contain at most
   `recommended_parallel_agents` Agent calls (default 6). Put only that wave's
   calls in the same message, wait for the whole wave, then start the next wave.
   **Never launch all slices at once.**
3. Use this short self-contained prompt for each Agent:

   ```text
   Read <skill-root>/references/summary-agent.md and follow it exactly.
   slice_id=<manifest slice id>
   expected_items=<manifest item count>
   input_path=<manifest input_path>
   output_path=<manifest output_path>
   Write and validate the output file. Return only DONE <slice_id> <count>.
   ```

4. Do not inline slice JSON or the full rules into Agent prompts. Each worker
   reads only the shared rule file and its small slice.
5. If an Agent reports 504/timeout/failure, finish the current waves first and
   retry only that slice once. If the retry fails again, process that bounded
   slice in the main thread. Never restart completed slices.
6. A `DONE` response is not proof that a file is complete. Step 6 performs the
   authoritative JSON, coverage, field, and evidence checks.

**IMPORTANT:** Don't dump summaries to chat. Each worker writes directly to its
manifest-provided part file.

### Step 6 — Validate and merge summary parts

Run the deterministic merger:

```powershell
uv run python -m ai_daily_digest.main merge-summaries --quiet
```

Success prints:

```text
SUMMARIES_READY summaries=N path=... report=...
```

On failure it prints `MERGE_INCOMPLETE` and writes `merge-report.json`. Read the
report, rerun only the listed `failed_slices`, then run `merge-summaries` again.
The merger leaves any existing complete `summaries.json` untouched until all
parts pass. **Do not run `apply` until `SUMMARIES_READY` is printed.**

Do not manually concatenate JSON and do not bypass a parse, coverage, or
evidence error. The merger requires exactly one valid summary for every URL.

### Step 7 — Run the `apply` stage

```powershell
uv run python -m ai_daily_digest.main apply --quiet
```

This prints:

```
DIGEST_READY html=... wiki=... items=N deduped=D summaries_applied=P
```

Parse to get the HTML path. Because Step 6 requires complete evidence-matched
parts, `real` must equal `summaries_applied` and `fallback` must be `0`. If not,
stop and repair the reported mismatch before continuing.

### Step 8 — Open the HTML and report back

**macOS/Linux:**
```bash
open "<the html path>"
```

**Windows:**
```powershell
Invoke-Item "<the html path>"
```

Use the command appropriate for the current platform, then report back.

Short Chinese summary (2-3 lines):

> 今日 AI 简报已生成：**N 条已验证内容**（去重 D 条，淘汰 I 个失效/不可读链接），已完成 **P 条**网页正文摘要。
> - AI 产品方法 X · 大模型边界 X · AI 评测 X · 重要论文 X · AI 新闻 X · GitHub 热门 X · 大模型动态 X · Claude Code X · Codex X
> - 已在浏览器中打开 `digest-YYYY-MM-DD.html`；Wiki 归档：`data\wiki\YYYY-MM-DD.md`

Per-category counts come from `data/wiki/YYYY-MM-DD.md`'s `## Contents` section. **Do not invent numbers.**

## Constraints

- **Don't echo summaries in chat.** Write only to manifest-provided part files. The HTML is the user-facing artifact.
- **Don't ask the user before running.** The skill is "say-and-show".
- **Don't skip Step 5.** Every manifest item must receive a summary, even when there are only a few items.
- **Don't summarize discovery snippets or titles.** Use only each item's verified `content.text` and copy its evidence fields exactly.
- **Don't invent URLs or paths.** Parse the manifest path from `COLLECT_READY`, slice paths from the manifest, and final paths from `SUMMARIES_READY` / `DIGEST_READY`.
- **Don't exceed the manifest concurrency limit.** More simultaneous requests can overload the inference gateway and make the run slower.

## Edge cases

- **Network/API failure during collect**: per-source failures are logged but don't abort. Broken, blocked, oversized, or unreadable pages are listed under `items.json::link_validation.failures` and excluded from `pending.json`.
- **Summary evidence mismatch**: `merge-summaries` rejects the affected slice before `apply`. Regenerate only the slice named in `merge-report.json`.
- **No new items today** (`pending=0`): skip Step 5, run `merge-summaries`, then `apply` (produces an HTML showing "本类今日无新内容" in each tab). Tell user this is normal — the dedup is working.
- **Re-run same day**: collect rebuilds the manifest and clears stale part files. Summarize only the new manifest; a prior complete `summaries.json` is replaced only after the new merge succeeds.
- **Same URL, new version**: version-aware dedup lets the item resurface. Always use the new `content.text` and evidence fields; never reuse the prior summary.
- **Repeated gateway timeout**: retry that bounded slice once after other waves finish; on a second failure, complete only that slice in the main thread.

## Project layout (for reference)

```
src/ai_daily_digest/
├── main.py            # collect / prepare-slices / merge-summaries / apply
├── summary_batches.py # bounded slicing + strict part validation/merge
├── sources/           # category fetchers + reddit (multi-category)
│   ├── product_learning.py  # auto-updating, source-tiered learning feeds
│   ├── arxiv.py, ai_news.py, github_trending.py, llm_updates.py, claude_code.py, codex.py
│   └── reddit.py      # routes subreddits → related categories
├── models.py          # Item, CATEGORIES, CATEGORY_LABELS
├── dedupe.py          # SQLite seen-set
├── scoring.py         # importance heuristic
├── web_content.py     # link verification, page extraction, cache, version evidence
├── render_html.py     # Jinja2 → tabbed HTML; _split_hype handles ⚠️ line
└── render_wiki.py     # markdown archive
output/
├── digest-DATE.items.json       # full snapshot from collect
├── digest-DATE.pending.json     # bounded summary input
├── slices/DATE/manifest.json    # exact work queue and concurrency limit
├── digest-DATE.summaries.part-*.json # one validated worker output per slice
├── digest-DATE.summaries.json   # atomically merged complete output
└── digest-DATE.html             # final, opened in Step 8
references/summary-agent.md      # shared worker rules
data/wiki/DATE.md                # markdown archive
data/seen.db                     # incremental dedup state
data/content-cache/              # conditional-GET cache, ignored by Git
```

## Manual invocation (debugging only)

```bash
cd ~/.claude/skills/ai-daily-digest

# Collect also creates bounded slices and a manifest:
uv run python -m ai_daily_digest.main collect --quiet
uv run python -m ai_daily_digest.main collect --limit-per-source 20 --top-k-summary 3

# Rebuild slices from an existing pending file:
uv run python -m ai_daily_digest.main prepare-slices --date 2026-05-18

# After all manifest part files are written:
uv run python -m ai_daily_digest.main merge-summaries --date 2026-05-18
uv run python -m ai_daily_digest.main apply --quiet

# Only fetch certain categories:
uv run python -m ai_daily_digest.main collect --categories pm_practice,model_limits,ai_evals --quiet

# Override date:
uv run python -m ai_daily_digest.main collect --date 2026-05-18 --quiet
```
