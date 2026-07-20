"""SQLite-backed seen-set: lets us run daily without re-surfacing yesterday's items.

Why SQLite vs JSON: O(1) lookup at any size, atomic writes, free.
URLs identify a source; source versions let materially updated pages resurface.
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterable

from .models import Item


SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    key_hash TEXT PRIMARY KEY,
    url      TEXT NOT NULL,
    category TEXT NOT NULL,
    title    TEXT,
    first_seen_date TEXT NOT NULL,
    source_version TEXT,
    content_sha256 TEXT
);
CREATE INDEX IF NOT EXISTS idx_seen_date ON seen(first_seen_date);
"""


def _hash(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


class SeenStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        with self._conn() as c:
            c.executescript(SCHEMA)
            columns = {row[1] for row in c.execute("PRAGMA table_info(seen)")}
            if "source_version" not in columns:
                c.execute("ALTER TABLE seen ADD COLUMN source_version TEXT")
            if "content_sha256" not in columns:
                c.execute("ALTER TABLE seen ADD COLUMN content_sha256 TEXT")

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def filter_new(self, items: Iterable[Item]) -> list[Item]:
        """Return unseen URLs and URLs whose meaningful source version changed.

        Rows created by versions before 0.2 have no source metadata. Backfill
        those rows without resurfacing the entire historical set at once.
        """
        items = list(items)
        if not items:
            return []
        keys = [_hash(it.dedup_key()) for it in items]
        placeholders = ",".join("?" * len(keys))
        with self._conn() as c:
            rows = c.execute(
                f"SELECT key_hash, source_version FROM seen WHERE key_hash IN ({placeholders})", keys
            ).fetchall()
            existing = {row[0]: row[1] for row in rows}
            legacy_updates = [
                (it.source_version, it.provenance.get("content_sha256"), key)
                for it, key in zip(items, keys)
                if key in existing and existing[key] is None and it.source_version
            ]
            if legacy_updates:
                c.executemany(
                    "UPDATE seen SET source_version=?, content_sha256=? WHERE key_hash=?",
                    legacy_updates,
                )

        fresh = []
        for item, key in zip(items, keys):
            if key not in existing:
                fresh.append(item)
            elif existing[key] is not None and existing[key] != item.source_version:
                fresh.append(item)
        return fresh

    def record(self, items: Iterable[Item], on_date: date) -> int:
        rows = [
            (
                _hash(it.dedup_key()), it.url, it.category, it.title,
                on_date.isoformat(), it.source_version,
                it.provenance.get("content_sha256"),
            )
            for it in items
        ]
        if not rows:
            return 0
        with self._conn() as c:
            c.executemany(
                """INSERT INTO seen(
                       key_hash,url,category,title,first_seen_date,source_version,content_sha256
                   ) VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(key_hash) DO UPDATE SET
                       url=excluded.url,
                       category=excluded.category,
                       title=excluded.title,
                       source_version=excluded.source_version,
                       content_sha256=excluded.content_sha256""",
                rows,
            )
        return len(rows)

    def stats(self) -> dict:
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM seen").fetchone()[0]
            by_cat = dict(
                c.execute(
                    "SELECT category, COUNT(*) FROM seen GROUP BY category"
                ).fetchall()
            )
        return {"total": total, "by_category": by_cat}
