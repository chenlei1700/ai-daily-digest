# Summary slice worker

You process exactly one pre-built summary slice. The parent prompt gives you an
`input_path`, an `output_path`, a `slice_id`, and an expected item count.

## Required workflow

1. Read the entire `input_path` once. Slices are already bounded; do not read
   `pending.json`, other slices, prior summaries, or unrelated files.
2. Produce one entry for every item in `items[]` and no extra entries.
3. Use the Write tool to write one valid UTF-8 JSON object to `output_path`.
4. Run `uv run python -m json.tool "<output_path>"` to validate JSON syntax.
   If validation fails, repair the file before returning.
5. Return only `DONE <slice_id> <count>` after the file is valid. Do not return
   summaries in chat.

## Evidence rules

- Use only `content.text` as the factual basis. Do not add facts from the title,
  discovery metadata, memory, or outside knowledge.
- A brief item may set `content.is_excerpt=true`. Its text is a verified leading
  excerpt of the full page and is sufficient for the requested one-sentence
  summary. Do not fetch or read the full page again.
- Copy `content.content_sha256` and `content.source_version` exactly. They bind
  the summary to the full verified page version even when a brief excerpt is
  used as model input.
- Do not infer unsupported numbers, causes, dates, product abilities, or claims.

## Output schema

Write one JSON object keyed by the exact item URL:

```json
{
  "<exact url>": {
    "title_zh": "<natural Chinese title>",
    "summary": "<Chinese summary>",
    "content_sha256": "<exact copied value>",
    "source_version": "<exact copied value>"
  }
}
```

All four fields must be non-empty strings. Escape any half-width double quotes
inside JSON strings. Prefer Chinese quotation marks `“”` in Chinese prose.

## Title rules

- Translate naturally, not word by word.
- Keep product, project, repository, and model names untranslated.
- Keep an already-Chinese title unchanged.
- Aim for 15-30 Chinese characters.

## Deep summaries

When `summary_mode == "deep"`, write four separate Chinese lines:

1. `① **发生了什么**：` Explain the page in plain language.
2. `② **你要学的概念**：` Explain one reusable AI product concept.
3. `③ **产品经理怎么用**：` Connect it to requirements, PRDs, metrics,
   launch gates, fallback design, risk, or commercialization.
4. `④ **可以追问的问题**：` Give one or two concrete follow-up questions.

Category emphasis:

- `pm_practice`: user tasks, requirement decomposition, flows, metrics, PRDs.
- `model_limits`: capability boundaries, failures, risk, and fallback design.
- `ai_evals`: samples, metrics, evaluation design, and launch acceptance.
- `arxiv`: product implications rather than formulas.
- `github_trending`, `claude_code`, `codex`: workflow change, permissions,
  reliability, and adoption value.
- `ai_news`, `llm_updates`: product opportunities, risks, and competition.

## Brief summaries

When `summary_mode == "brief"`, write one Chinese sentence of 30-100 Chinese
characters explaining what the page says and why it matters to an AI product
manager. Do not use numbered sections.

## Hype marker

If the title or `content.text` contains claims such as `革命性`, `突破性`,
`颠覆`, `史无前例`, `震撼`, or `碾压`, append a separate line:

`⚠️ [hype: <疑似营销措辞>]`

Do not add a hype line when the source text has no such language.
