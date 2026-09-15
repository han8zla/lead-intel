from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class UnknownSignalRegistry:
    """Persistent registry for validating and promoting previously unknown observations."""

    def __init__(self, db_path: str = "./data/lead_intelligence.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)

    def setup_tables(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS signal_registry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    classification TEXT NOT NULL DEFAULT 'KNOWN',
                    description TEXT,
                    pattern_json TEXT NOT NULL,
                    validation_source TEXT,
                    occurrence_count INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_signal_registry_classification ON signal_registry(classification)"
            )
            conn.commit()
        finally:
            conn.close()

    def promote(
        self,
        *,
        fingerprint: str,
        name: str,
        pattern: dict,
        description: str | None = None,
        validation_source: str = "human",
    ) -> int:
        """Promote a validated unknown observation into the reusable signal library."""
        self.setup_tables()
        fingerprint = fingerprint.strip()
        name = name.strip()
        if not fingerprint or not name:
            raise ValueError("Signal fingerprint and name are required")

        now = self._now()
        conn = self._connect()
        try:
            existing = conn.execute(
                "SELECT id FROM signal_registry WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE signal_registry
                       SET name = ?, description = ?, pattern_json = ?,
                           validation_source = ?, classification = 'KNOWN', enabled = 1,
                           updated_at = ?
                       WHERE id = ?""",
                    (name, description, self._json(pattern), validation_source, now, existing["id"]),
                )
                conn.commit()
                return int(existing["id"])

            cursor = conn.execute(
                """INSERT INTO signal_registry
                   (fingerprint, name, classification, description, pattern_json,
                    validation_source, occurrence_count, enabled, created_at, updated_at)
                   VALUES (?, ?, 'KNOWN', ?, ?, ?, 0, 1, ?, ?)""",
                (fingerprint, name, description, self._json(pattern), validation_source, now, now),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def record_occurrence(self, fingerprint: str) -> bool:
        """Increment usage of a validated reusable signal."""
        self.setup_tables()
        conn = self._connect()
        try:
            cursor = conn.execute(
                """UPDATE signal_registry
                   SET occurrence_count = occurrence_count + 1, updated_at = ?
                   WHERE fingerprint = ? AND enabled = 1""",
                (self._now(), fingerprint),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def list_signals(self, *, enabled_only: bool = True) -> list[dict]:
        self.setup_tables()
        conn = self._connect()
        try:
            sql = "SELECT * FROM signal_registry"
            if enabled_only:
                sql += " WHERE enabled = 1"
            sql += " ORDER BY occurrence_count DESC, id"
            rows = conn.execute(sql).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["pattern"] = json.loads(item.pop("pattern_json"))
                item["enabled"] = bool(item["enabled"])
                result.append(item)
            return result
        finally:
            conn.close()

    def get_by_fingerprint(self, fingerprint: str) -> dict | None:
        self.setup_tables()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM signal_registry WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            if not row:
                return None
            item = dict(row)
            item["pattern"] = json.loads(item.pop("pattern_json"))
            item["enabled"] = bool(item["enabled"])
            return item
        finally:
            conn.close()
