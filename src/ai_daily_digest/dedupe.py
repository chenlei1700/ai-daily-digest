"""SQLite-backed seen-set: lets us run daily without re-surfacing yesterday's items.

Why SQLite vs JSON: O(1) lookup at any size, atomic writes, free.
Why URL hash vs title: titles drift (e.g. "[Update]" prefixes), URLs are stable.
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
    first_seen_date TEXT NOT NULL
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

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def filter_new(self, items: Iterable[Item]) -> list[Item]:
        """Return only items whose dedup_key isn't already in the store."""
        items = list(items)
        if not items:
            return []
        keys = [_hash(it.dedup_key()) for it in items]
        placeholders = ",".join("?" * len(keys))
        with self._conn() as c:
            rows = c.execute(
                f"SELECT key_hash FROM seen WHERE key_hash IN ({placeholders})", keys
            ).fetchall()
        already = {r[0] for r in rows}
        return [it for it, k in zip(items, keys) if k not in already]

    def record(self, items: Iterable[Item], on_date: date) -> int:
        rows = [
            (_hash(it.dedup_key()), it.url, it.category, it.title, on_date.isoformat())
            for it in items
        ]
        if not rows:
            return 0
        with self._conn() as c:
            c.executemany(
                "INSERT OR IGNORE INTO seen(key_hash,url,category,title,first_seen_date) VALUES (?,?,?,?,?)",
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
