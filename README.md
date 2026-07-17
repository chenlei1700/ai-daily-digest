# ai-daily-digest

A Claude Code skill that collects daily AI-domain updates and turns them into a learning-oriented brief for junior AI product managers: model limits, AI evaluation, product requirements, industry news, tools, papers, and platform updates — **all from a single phrase like "AI 日报"**.

![Sample HTML output](docs/screenshot.png)

_Actual local run on 2026-07-17: 118 items across 9 learning categories, with 65 previously exposed items removed by incremental deduplication._

> Browse a [live sample HTML](examples/digest-example.html) (open in browser after clone) · or the [grep-friendly markdown wiki](examples/wiki-example.md) archive.

## What changed in this fork

Compared with the upstream `chenlei1700/ai-daily-digest`, this fork turns a general AI news brief into a learning and decision-support workflow for AI product managers:

- **AI PM learning layer:** adds three fixed curriculum categories for product methods, model limits, and AI evaluation, with each deep summary rewritten as “what happened - concept - PM use - follow-up questions”.
- **Exposure-aware deduplication:** only deep items enter `seen.db`; brief candidates can compete again on later days instead of being permanently consumed as soon as they are fetched.
- **Higher-signal source strategy:** uses Hugging Face Daily Papers as the primary paper-discovery path with arXiv fallback, enriches GitHub metadata, and adds official/fallback paths for Claude Code and Codex updates.
- **Concurrent summarization workflow:** splits large pending batches by category, writes independent summary parts, verifies coverage, and retries only failed slices instead of serially processing one large JSON payload.
- **Failure recovery and conservative fallback:** merges valid part files, detects missing or placeholder summaries, surfaces fallback ratios, and still produces a usable digest when one summarization slice fails.
- **Operational automation:** improves GitHub authentication guidance, scheduled token injection, launchd installation, output lifecycle cleanup, and HTML + Markdown Wiki generation for both daily reading and long-term retrieval.

The design goal is not to maximize the number of fetched links. It is to help an AI product manager repeatedly practice requirement framing, model-boundary judgment, evaluation design, and product application while keeping the workflow observable and recoverable.

## What it does

```
[ Python: collect ]  →  pending.json  →  [ Claude: summarize ]  →  summaries.json  →  [ Python: apply ]  →  HTML
```

When you say "AI 日报" / "今日 AI 简报" / "daily ai digest" in Claude Code, the skill:

1. **Fetches** from AI PM curriculum cards, HN, arXiv, GitHub, official AI blogs, Reddit, Claude Code, and Codex sources
2. **Deduplicates** previously deep-read news against `data/seen.db`, while keeping the fixed learning curriculum available for deliberate review
3. **Ranks** items by learning value and signal strength
4. **Claude itself writes AI-PM-oriented summaries** — no extra LLM API call from Python
5. **Renders** a single-file HTML with learning tabs + a markdown archive

### Categories

| Category | What you learn | Sources |
|---|---|---|
| AI 产品方法 | 需求拆解、PRD、用户任务、指标、人工兜底、Agent 产品设计 | Built-in curriculum cards |
| 大模型边界 | 幻觉、Prompt Injection、上下文、记忆、权限、安全和失败模式 | Built-in curriculum cards |
| AI 评测 | 离线评测、A/B、黄金集、回归集、LLM-as-judge、上线门槛 | Built-in curriculum cards |
| 重要论文 | 把研究进展翻译成产品能力和未来机会 | arXiv / Hugging Face Daily Papers |
| AI 新闻 | 行业变化、竞品动向、监管和商业化风险 | Hacker News + r/MachineLearning + r/singularity |
| GitHub 热门 | 新工具、新工作流、新开源项目 | GitHub Trending filtered for AI relevance |
| 大模型动态 | 模型发布、能力变化、价格/API、benchmark | Simon Willison RSS + OpenAI / Google DeepMind official blogs + HN keyword search |
| Claude Code | AI coding agent 能力变化与工作流影响 | `anthropics/claude-code` releases + commits + r/ClaudeAI |
| Codex | OpenAI Codex CLI / agent 工具变化 | OpenAI Codex releases/commits and related updates |

Reddit sources are optional — see "Reddit fallback chain" below.

## Sample output

The HTML brief is a single-file, dependency-free page with learning tabs:

```
┌─ AI Daily Digest ────────────────────────────────────────────┐
│ 2026-05-19 · 共 66 条（已增量去重 0 条）                       │
├──────────────────────────────────────────────────────────────┤
│ [重要论文 15] [AI 新闻 15] [GitHub 热门 8]                     │
│ [大模型动态 13] [Claude Code 15] [Codex 5]                    │
├──────────────────────────────────────────────────────────────┤
│ ╭──────────────────────────────────────────────────╮ ★ 64.6 │
│ │ DashAttention：可微的自适应稀疏分层注意力             │       │
│ │ (DashAttention: Differentiable and Adaptive ...) │       │
│ │ arXiv · Yuxiang Huang · 2026-05-18                │       │
│ │ ─────────────────────────────────────────────    │       │
│ │ ① 事实：提出端到端可微的稀疏分层注意力 ...           │       │
│ │ ② 你要学的概念：这是一次模型能力边界变化 ...         │       │
│ │ ③ 产品经理怎么用：把它转成需求、指标和兜底 ...       │       │
│ │ ④ 可以追问的问题：上线前如何验证失败率？             │       │
│ ╰──────────────────────────────────────────────────╯       │
│ ╭──────────────────────────────────────────────────╮ ★ 198 │
│ │ openclaw/openclaw — Your own personal AI assist...│       │
│ │ ⚠️ [hype: "Any OS. Any Platform. The lobster way"]│       │
│ ╰──────────────────────────────────────────────────╯       │
│ ...                                                          │
└──────────────────────────────────────────────────────────────┘
```

Three artifact files per day:

| File | Purpose |
|---|---|
| [`examples/digest-example.html`](examples/digest-example.html) | Tabbed HTML brief — open in browser, no external dependencies |
| [`examples/wiki-example.md`](examples/wiki-example.md) | Long-term grep-able markdown archive |
| `output/digest-DATE.items.json` | Raw fetched items + scores (internal) |

The HTML has a dark theme that respects your OS theme, displays Chinese titles with English originals in muted text, four-section learning summaries for top items, single-sentence briefs for the rest, and `⚠️ [hype: ...]` annotations when titles contain marketing buzzwords.

## Output

```
output/
├── digest-YYYY-MM-DD.html               # tabbed brief, opened in browser
├── digest-YYYY-MM-DD.items.json         # full snapshot
├── digest-YYYY-MM-DD.pending.json       # what Claude needs to summarize
└── digest-YYYY-MM-DD.summaries.json     # Claude's output
data/
├── wiki/YYYY-MM-DD.md                   # markdown archive (grep-friendly)
└── seen.db                              # incremental dedup
```

The HTML has:
- Learning tabs sorted by importance score
- Chinese titles with English originals in parentheses
- Four-section learning summaries for top items: what happened, concept, PM use, follow-up questions
- One-sentence brief summaries for the rest
- ⚠️ `[hype: ...]` annotations when titles contain marketing buzzwords

## Install

### Prerequisites

1. **Claude Code CLI** — [Install from anthropics/claude-code](https://github.com/anthropics/claude-code)
2. **Python 3.11+** and **[uv](https://docs.astral.sh/uv/)**
3. **GitHub CLI (recommended)** — Without it, GitHub-backed sources may be sparse due to GitHub API limits. Claude Code releases also have Atom/npm fallbacks, but `gh` is still recommended:
   ```bash
   brew install gh
   gh auth login
   ```
4. **ANTHROPIC_AUTH_TOKEN** — Add to your shell rc file (`~/.zshrc` or `~/.bashrc`):
   ```bash
   export ANTHROPIC_AUTH_TOKEN="sk-ant-..."
   export ANTHROPIC_BASE_URL="https://api.anthropic.com"  # or your relay URL
   ```

### Quick Install (macOS/Linux)

```bash
# Clone the fork, then enter the directory
git clone https://github.com/1572135825-prog/ai-daily-digest.git
cd ai-daily-digest

# Install Python dependencies
uv sync

# Run interactive installer
./install.sh
```

The installer will:
- Check all dependencies and guide you through missing ones
- Copy launcher script to `~/.local/bin/`
- Link this directory into `~/.claude/skills/ai-daily-digest`
- Generate launchd plists for daily digest (09:07) and cleanup (21:00)
- Create `.claude/settings.json` for auto-permissions
- Load the digest job and install 21:00 cleanup via launchd, with crontab fallback if launchd refuses the cleanup job

Cleanup removes expired generated files under `output/` and `data/wiki/` after 24 hours. If both launchd and crontab refuse the 21:00 cleanup scheduler, the digest launcher still runs cleanup before each scheduled 09:07 digest as a last-resort fallback.

### Manual Install

If you prefer manual setup or are on Windows:

```bash
# 1. Symlink to Claude Code skills directory
ln -s "$(pwd)" ~/.claude/skills/ai-daily-digest

# 2. Create project-level permissions (avoids launchd hanging on Agent tool)
mkdir -p .claude
cat > .claude/settings.json << 'EOF'
{
  "permissions": {
    "allowed": [
      {"type": "prompt", "tool": "Agent", "prompt": "*"}
    ]
  }
}
EOF

# 3. For launchd automation, manually edit and load the plist template
#    (see install.sh for reference)
```

## Use

This is a Claude Code skill. The recommended way is to symlink/copy it to your global skills directory:

```bash
# Windows
mklink /D "%USERPROFILE%\.claude\skills\ai-daily-digest" "<path-to-this-repo>"

# Linux/Mac
ln -s <path-to-this-repo> ~/.claude/skills/ai-daily-digest
```

Then in any Claude Code session say:

> AI 日报

Claude will run the full pipeline and open the HTML in your browser. See `SKILL.md` for the trigger phrase list and exact flow.

### Manual invocation (for debugging)

```bash
uv run python -m ai_daily_digest.main collect --quiet
# Claude writes summaries to output/digest-DATE.summaries.json
uv run python -m ai_daily_digest.main apply --quiet
```

CLI flags:
- `--limit-per-source N` — items per source (default 30)
- `--top-k-summary N` — items per category to get deep summary (default 5)
- `--categories arxiv,claude_code` — only fetch certain categories
- `--date YYYY-MM-DD` — override date
- `--quiet` — silence httpx logs

## Reddit fallback chain

Reddit blocks anonymous JSON API access in 2024+, so the skill tries four tiers in order:

1. **`data/reddit_cookie.txt`** — paste Cookie header from your browser (manual, ~1-2 weeks before re-copy)
2. **`REDDIT_COOKIE` env var** — same content as the file, but as env var (subject to setx 1024-char limit)
3. **Anonymous old.reddit.com HTML scraping** — works ~50% of the time due to Reddit's IP-based rate limiting
4. **`browser_cookie3`** auto-read from Firefox/Brave/etc — Chrome/Edge 124+ blocked by App-Bound Encryption

If all fail, the HTML shows an orange banner prompting login. To skip Reddit entirely: create empty file `data/reddit_disabled`.

## Customize the scoring or prompt

These are the two design knobs that determine output quality:

- **Scoring** (`src/ai_daily_digest/scoring.py::score_item`) — decides ordering within each category. Default calibration: HN 1000 pts ≈ GitHub 10k stars ≈ score 100. Tweak weights for big-lab keywords (Anthropic / DeepMind / etc), recency decay, etc.
- **Summary prompt** (`SKILL.md`, Step 4) — embedded directly in the skill so Claude reads & applies it each run. Adjust tone, length, hype-detection rules. For large pending batches, the skill now requires concurrent subagents to keep launchd/Claude Code runs from hanging or taking 40+ minutes.

## Architecture

```
src/ai_daily_digest/
├── main.py            # collect / apply subcommands
├── sources/           # one module per source
│   ├── product_learning.py  (AI PM curriculum cards)
│   ├── arxiv.py
│   ├── ai_news.py     (Hacker News Algolia)
│   ├── github_trending.py  (HTML scrape of /trending?since=weekly)
│   ├── llm_updates.py  (Simon Willison + official AI lab blogs + HN keyword search)
│   ├── claude_code.py
│   ├── codex.py
│   └── reddit.py      (4-tier fallback)
├── models.py          # Item dataclass + categories
├── dedupe.py          # SQLite seen-set
├── scoring.py         # importance heuristic
├── render_html.py     # Jinja2 → single-file HTML
└── render_wiki.py     # markdown archive
```

## License

MIT
