import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_daily_digest.summary_batches import (
    compact_pending_item,
    merge_summary_parts,
    write_summary_slices,
)


def _pending_item(index: int, mode: str, text: str) -> dict:
    return {
        "url": f"https://example.com/item-{index}",
        "category": "ai_news",
        "title": f"Item {index}",
        "source": "Example",
        "score": 100 - index,
        "summary_mode": mode,
        "content": {
            "text": text,
            "content_chars": len(text),
            "content_sha256": f"hash-{index}",
            "source_version": f"version-{index}",
        },
    }


def _valid_summary(item: dict) -> dict:
    return {
        "title_zh": f"条目：{item['title']}",
        "summary": "网页说明了一个经过验证的 AI 产品变化。",
        "content_sha256": item["content"]["content_sha256"],
        "source_version": item["content"]["source_version"],
    }


class SummaryBatchTests(unittest.TestCase):
    def test_brief_input_is_bounded_without_changing_page_evidence(self):
        text = "verified page text " * 700
        brief = _pending_item(1, "brief", text)
        deep = _pending_item(2, "deep", text)

        compact_brief = compact_pending_item(brief, 1_000)
        compact_deep = compact_pending_item(deep, 1_000)

        self.assertLessEqual(len(compact_brief["content"]["text"]), 1_000)
        self.assertGreaterEqual(len(compact_brief["content"]["text"]), 800)
        self.assertEqual(compact_brief["content"]["full_content_chars"], len(text))
        self.assertTrue(compact_brief["content"]["is_excerpt"])
        self.assertEqual(compact_brief["content"]["content_sha256"], "hash-1")
        self.assertEqual(compact_deep["content"]["text"], text)
        self.assertFalse(compact_deep["content"]["is_excerpt"])

    def test_slices_are_bounded_by_input_size_and_item_count(self):
        items = [
            _pending_item(i, "deep" if i < 2 else "brief", "body " * 130)
            for i in range(9)
        ]
        pending = {"date": "2026-07-21", "items": items}

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            pending_path = root / "digest-2026-07-21.pending.json"
            pending_path.write_text(json.dumps(pending), encoding="utf-8")
            manifest, manifest_path = write_summary_slices(
                pending,
                pending_path,
                root,
                brief_content_chars=400,
                slice_char_budget=2_400,
                slice_max_items=3,
                max_parallel_agents=4,
            )

            self.assertTrue(manifest_path.exists())
            self.assertEqual(manifest["total_items"], 9)
            self.assertEqual(manifest["recommended_parallel_agents"], 4)
            self.assertGreater(manifest["slice_count"], 1)
            self.assertEqual(sum(spec["items"] for spec in manifest["slices"]), 9)
            for spec in manifest["slices"]:
                self.assertLessEqual(spec["items"], 3)
                if not spec["oversized"]:
                    self.assertLessEqual(spec["input_chars"], 2_400)
                self.assertTrue(Path(spec["input_path"]).exists())

    def test_slice_concurrency_cannot_exceed_gateway_safe_limit(self):
        pending = {
            "date": "2026-07-21",
            "items": [_pending_item(1, "brief", "verified body")],
        }
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "must be <= 6"):
                write_summary_slices(
                    pending,
                    root / "digest-2026-07-21.pending.json",
                    root,
                    max_parallel_agents=7,
                )

    def test_merge_rejects_bad_parts_and_replaces_output_only_when_complete(self):
        pending = {
            "date": "2026-07-21",
            "items": [
                _pending_item(1, "brief", "first verified body"),
                _pending_item(2, "brief", "second verified body"),
            ],
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            pending_path = root / "digest-2026-07-21.pending.json"
            pending_path.write_text(json.dumps(pending), encoding="utf-8")
            manifest, manifest_path = write_summary_slices(
                pending,
                pending_path,
                root,
                slice_char_budget=10_000,
                slice_max_items=1,
            )
            summaries_path = root / "digest-2026-07-21.summaries.json"
            original = {"existing": {"summary": "do not replace on failure"}}
            summaries_path.write_text(json.dumps(original), encoding="utf-8")

            for index, spec in enumerate(manifest["slices"]):
                slice_payload = json.loads(Path(spec["input_path"]).read_text(encoding="utf-8"))
                item = slice_payload["items"][0]
                if index == 0:
                    Path(spec["output_path"]).write_text(
                        json.dumps({item["url"]: _valid_summary(item)}), encoding="utf-8"
                    )
                else:
                    Path(spec["output_path"]).write_text("{bad json", encoding="utf-8")

            failed = merge_summary_parts(manifest_path, summaries_path)
            self.assertFalse(failed["ok"])
            self.assertEqual(json.loads(summaries_path.read_text(encoding="utf-8")), original)
            self.assertEqual(len(failed["failed_slices"]), 1)

            failed_spec = manifest["slices"][1]
            failed_payload = json.loads(
                Path(failed_spec["input_path"]).read_text(encoding="utf-8")
            )
            failed_item = failed_payload["items"][0]
            stale_summary = _valid_summary(failed_item)
            stale_summary["content_sha256"] = "stale-hash"
            Path(failed_spec["output_path"]).write_text(
                json.dumps({failed_item["url"]: stale_summary}),
                encoding="utf-8",
            )

            stale = merge_summary_parts(manifest_path, summaries_path)
            self.assertFalse(stale["ok"])
            self.assertIn(
                "content_sha256 mismatch",
                " ".join(stale["failed_slices"][0]["reasons"]),
            )
            self.assertEqual(json.loads(summaries_path.read_text(encoding="utf-8")), original)

            Path(failed_spec["output_path"]).write_text(
                json.dumps({failed_item["url"]: _valid_summary(failed_item)}),
                encoding="utf-8",
            )

            complete = merge_summary_parts(manifest_path, summaries_path)
            self.assertTrue(complete["ok"])
            merged = json.loads(summaries_path.read_text(encoding="utf-8"))
            self.assertEqual(set(merged), {item["url"] for item in pending["items"]})


if __name__ == "__main__":
    unittest.main()
