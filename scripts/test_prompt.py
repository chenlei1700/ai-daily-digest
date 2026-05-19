"""Cheap single-call test for the SUMMARY_PROMPT shape.

Run after `setx ANTHROPIC_API_KEY ...` (PowerShell) or `$env:ANTHROPIC_API_KEY=...`.
Costs roughly $0.001 (one Haiku call).

Usage:
  uv run python scripts/test_prompt.py
"""
from __future__ import annotations

import os
import sys

# Add src to path when run directly
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src"))

from ai_daily_digest.summarize import SUMMARY_PROMPT


SAMPLE = {
    "category_label": "重要论文",
    "title": "DashAttention: Differentiable and Adaptive Sparse Hierarchical Attention",
    "source": "arXiv",
    "raw": (
        "Current hierarchical attention methods, such as NSA and InfLLMv2, select "
        "the top-k relevant key-value (KV) blocks based on coarse attention scores "
        "and subsequently apply fine-grained softmax attention on the selected tokens. "
        "However, the top-k operation assumes the number of relevant tokens for any "
        "query is fixed and it precludes the gradient flow between the sparse and "
        "dense stages. In this work, we present DashAttention, a revolutionary "
        "differentiable hierarchical attention that achieves state-of-the-art "
        "performance on long-context benchmarks."
    ),
}


def main() -> int:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: set ANTHROPIC_API_KEY first", file=sys.stderr)
        return 2
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    print("Sending one Haiku request ...\n")
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": SUMMARY_PROMPT.format(**SAMPLE)}],
    )
    print("─" * 60)
    print(msg.content[0].text)
    print("─" * 60)
    print(f"input tokens : {msg.usage.input_tokens}")
    print(f"output tokens: {msg.usage.output_tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
