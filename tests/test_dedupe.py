from datetime import date
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from ai_daily_digest.dedupe import SeenStore
from ai_daily_digest.models import Item


def versioned_item(version: str, digest: str = "hash") -> Item:
    return Item(
        "ai_evals", "Guide", "https://example.com/guide", "Example",
        source_version=version,
        provenance={"content_sha256": digest},
    )


class SeenStoreTests(unittest.TestCase):
    def test_same_version_is_hidden_but_new_version_resurfaces(self):
        with TemporaryDirectory() as tmp:
            store = SeenStore(Path(tmp) / "seen.db")
            v1 = versioned_item("sha256:v1")
            self.assertEqual(store.filter_new([v1]), [v1])
            store.record([v1], date(2026, 7, 20))

            self.assertEqual(store.filter_new([versioned_item("sha256:v1")]), [])
            self.assertEqual(
                store.filter_new([versioned_item("sha256:v2")]),
                [versioned_item("sha256:v2")],
            )

    def test_legacy_row_is_migrated_and_backfilled_without_resurfacing(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "seen.db"
            with sqlite3.connect(db) as conn:
                conn.executescript(
                    """CREATE TABLE seen (
                        key_hash TEXT PRIMARY KEY, url TEXT NOT NULL,
                        category TEXT NOT NULL, title TEXT,
                        first_seen_date TEXT NOT NULL
                    );
                    INSERT INTO seen VALUES (
                        'd9a3e95fa91650646570911476a45f7bb8573178',
                        'https://example.com/guide', 'ai_evals', 'Guide', '2026-07-01'
                    );"""
                )
            store = SeenStore(db)

            self.assertEqual(store.filter_new([versioned_item("sha256:v1")]), [])
            with sqlite3.connect(db) as conn:
                version = conn.execute("SELECT source_version FROM seen").fetchone()[0]
            self.assertEqual(version, "sha256:v1")


if __name__ == "__main__":
    unittest.main()
