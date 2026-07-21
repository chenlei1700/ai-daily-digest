from datetime import datetime, timezone
import unittest

from ai_daily_digest.models import Item


class ItemSerializationTests(unittest.TestCase):
    def test_round_trip_preserves_content_evidence(self):
        now = datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc)
        item = Item(
            category="ai_evals",
            title="Evaluation guide",
            url="https://example.com/evals",
            source="Example",
            published_at=now,
            content="Verified page body",
            source_version="etag:v1|sha256:abc",
            retrieved_at=now,
            provenance={"status": "verified", "content_sha256": "abc"},
        )

        restored = Item.from_dict(item.to_dict())

        self.assertEqual(restored, item)


if __name__ == "__main__":
    unittest.main()
