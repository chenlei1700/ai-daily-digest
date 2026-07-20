from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from ai_daily_digest.sources import product_learning


class ProductLearningTests(unittest.TestCase):
    def test_track_discovers_recent_matching_feed_entries(self):
        entries = [{
            "title": "A practical AI evaluation workflow for product teams",
            "summary": "How users, metrics, and benchmark design shape product quality.",
            "link": "https://example.com/eval-workflow",
            "published_parsed": datetime(2026, 7, 20, tzinfo=timezone.utc).timetuple(),
        }]

        with patch.object(
            product_learning,
            "_load_feed",
            return_value=({"version": "feed-v1"}, entries),
        ):
            items = product_learning.fetch_ai_evals(limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://example.com/eval-workflow")
        self.assertTrue(items[0].raw_metrics["learning_material"])
        self.assertEqual(items[0].raw_metrics["feed_version"], "feed-v1")
        self.assertEqual(items[0].raw_metrics["source_config_version"], "2026-07-20.1")


if __name__ == "__main__":
    unittest.main()
