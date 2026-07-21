from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import ai_daily_digest.main as main_module
from ai_daily_digest.dedupe import SeenStore
from ai_daily_digest.main import _dedupe_batch, _summary_matches_source
from ai_daily_digest.models import Item
from ai_daily_digest.scoring import score_item


class PipelineContractTests(unittest.TestCase):
    def test_duplicate_learning_url_uses_best_track_match(self):
        first = Item(
            "pm_practice", "Shared", "https://example.com/shared", "Example",
            raw_metrics={"keyword_hits": ["product"]},
        )
        better = Item(
            "ai_evals", "Shared", "https://example.com/shared", "Example",
            raw_metrics={"keyword_hits": ["eval", "benchmark"]},
        )

        self.assertEqual(_dedupe_batch([first, better]), [better])

    def test_summary_must_match_page_hash_and_source_version(self):
        item = Item(
            "ai_evals", "Guide", "https://example.com/guide", "Example",
            source_version="etag:v2|sha256:abc",
            provenance={"content_sha256": "abc"},
        )
        valid = {
            "summary": "summary",
            "content_sha256": "abc",
            "source_version": "etag:v2|sha256:abc",
        }

        self.assertTrue(_summary_matches_source(valid, item))
        self.assertFalse(_summary_matches_source({**valid, "content_sha256": "old"}, item))
        self.assertFalse(_summary_matches_source({"summary": "legacy"}, item))

    def test_learning_score_uses_source_tier_and_keyword_relevance(self):
        item = Item(
            "pm_practice", "Guide", "https://example.com/guide", "Example",
            raw_metrics={
                "learning_material": True,
                "source_tier": "S",
                "keyword_hits": ["product", "workflow"],
            },
        )

        self.assertEqual(score_item(item), 88.0)

    def test_apply_records_only_real_evidence_matched_deep_summaries(self):
        run_date = date(2026, 7, 20)
        good = Item(
            "ai_evals", "Good", "https://example.com/good", "Example",
            content="verified text", source_version="sha256:v1",
            provenance={"status": "verified", "content_sha256": "good-hash"},
        )
        bad = Item(
            "ai_evals", "Bad", "https://example.com/bad", "Example",
            content="verified text", source_version="sha256:v1",
            provenance={"status": "verified", "content_sha256": "bad-hash"},
        )
        summaries = {
            good.url: {
                "title_zh": "有效摘要",
                "summary": "模型基于网页正文生成的摘要。",
                "content_sha256": "good-hash",
                "source_version": "sha256:v1",
            },
            bad.url: {
                "title_zh": "过期摘要",
                "summary": "这条摘要证据不匹配。",
                "content_sha256": "old-hash",
                "source_version": "sha256:v0",
            },
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            output_dir = root / "output"
            output_dir.mkdir()
            (output_dir / "digest-2026-07-20.items.json").write_text(
                json.dumps({
                    "date": "2026-07-20",
                    "deep_urls": [good.url, bad.url],
                    "items": [good.to_dict(), bad.to_dict()],
                }),
                encoding="utf-8",
            )
            (output_dir / "digest-2026-07-20.summaries.json").write_text(
                json.dumps(summaries), encoding="utf-8"
            )
            with patch.object(main_module, "DATA_DIR", data_dir), patch.object(
                main_module, "OUTPUT_DIR", output_dir
            ):
                self.assertEqual(main_module.run_apply(run_date, quiet=True), 0)

            store = SeenStore(data_dir / "seen.db")
            self.assertEqual(store.filter_new([good]), [])
            self.assertEqual(store.filter_new([bad]), [bad])

    def test_apply_requires_successful_merge_report_when_manifest_exists(self):
        run_date = date(2026, 7, 21)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            output_dir = root / "output"
            manifest_dir = output_dir / "slices" / "2026-07-21"
            manifest_dir.mkdir(parents=True)
            (manifest_dir / "manifest.json").write_text(
                json.dumps({"date": "2026-07-21", "total_items": 1, "slices": []}),
                encoding="utf-8",
            )

            with patch.object(main_module, "DATA_DIR", data_dir), patch.object(
                main_module, "OUTPUT_DIR", output_dir
            ):
                self.assertEqual(main_module.run_apply(run_date, quiet=True), 4)


if __name__ == "__main__":
    unittest.main()
