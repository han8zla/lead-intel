import json
import sqlite3
from typing import Any


class IntelligenceReader:
    """Read-only query boundary for Phase 4 intelligence data."""

    def __init__(self, db_path: str = "./data/lead_intelligence.db"):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _decode_json(value: str | None) -> Any:
        if value is None:
            return None
        return json.loads(value)

    @classmethod
    def _row(cls, row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        item = dict(row)
        for key in (
            "summary_json",
            "metadata_json",
            "value_json",
            "evidence_json",
            "context_json",
            "observation_json",
            "interpretation_json",
            "input_summary_json",
            "output_json",
            "unknowns_json",
            "attributes_json",
        ):
            if key in item:
                item[key.removesuffix("_json")] = cls._decode_json(item.pop(key))
        return item

    @classmethod
    def _rows(cls, rows: list[sqlite3.Row]) -> list[dict]:
        return [cls._row(row) for row in rows]

    def get_run(self, run_id: str) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM analysis_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            return self._row(row)
        finally:
            conn.close()

    def list_runs(self, *, lead_id: int | None = None, limit: int = 50) -> list[dict]:
        conn = self._connect()
        try:
            if lead_id is None:
                rows = conn.execute(
                    "SELECT * FROM analysis_runs ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM analysis_runs
                    WHERE lead_id = ?
                    ORDER BY started_at DESC
                    LIMIT ?
                    """,
                    (lead_id, limit),
                ).fetchall()
            return self._rows(rows)
        finally:
            conn.close()

    def get_run_pages(self, run_id: str) -> list[dict]:
        return self._query("SELECT * FROM analysis_pages WHERE run_id = ? ORDER BY id", (run_id,), ("metadata_json",))

    def get_run_observations(self, run_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM intelligence_observations WHERE run_id = ? ORDER BY id",
            (run_id,),
            ("value_json", "evidence_json"),
        )

    def get_run_signals(self, run_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM intelligence_signals WHERE run_id = ? ORDER BY id",
            (run_id,),
            ("evidence_json", "context_json"),
        )

    def get_run_unknowns(self, run_id: str, *, validation_status: str | None = None) -> list[dict]:
        if validation_status is None:
            return self._query(
                "SELECT * FROM unknown_signals WHERE run_id = ? ORDER BY id",
                (run_id,),
                ("observation_json", "context_json", "interpretation_json"),
            )
        return self._query(
            """
            SELECT * FROM unknown_signals
            WHERE run_id = ? AND validation_status = ?
            ORDER BY id
            """,
            (run_id, validation_status),
            ("observation_json", "context_json", "interpretation_json"),
        )

    def get_run_ai(self, run_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM ai_interpretations WHERE run_id = ? ORDER BY id",
            (run_id,),
            ("input_summary_json", "output_json"),
        )

    def get_run_opportunities(self, run_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM intelligence_opportunities WHERE run_id = ? ORDER BY score DESC, id",
            (run_id,),
            ("evidence_json", "unknowns_json"),
        )

    def get_run_timeline(self, run_id: str) -> list[dict]:
        rows = self._query(
            """
            SELECT id, run_id, lead_id, event_name, stage, severity,
                   message, attributes_json, created_at
            FROM audit_events
            WHERE run_id = ?
            ORDER BY id
            """,
            (run_id,),
            ("attributes_json",),
        )
        return rows

    def get_latest_runs(self, limit: int = 20) -> list[dict]:
        return self.list_runs(limit=limit)

    def get_system_health(self) -> dict:
        conn = self._connect()
        try:
            total = conn.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0]
            completed = conn.execute("SELECT COUNT(*) FROM analysis_runs WHERE status = 'COMPLETED'").fetchone()[0]
            failed = conn.execute("SELECT COUNT(*) FROM analysis_runs WHERE status = 'FAILED'").fetchone()[0]
            running = conn.execute("SELECT COUNT(*) FROM analysis_runs WHERE status = 'RUNNING'").fetchone()[0]
            return {
                "total_runs": total,
                "completed_runs": completed,
                "failed_runs": failed,
                "running_runs": running,
                "failure_rate": (failed / total) if total else 0.0,
            }
        finally:
            conn.close()

    def _query(self, sql: str, params: tuple, json_columns: tuple[str, ...]) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                for column in json_columns:
                    if column in item:
                        key = column.removesuffix("_json")
                        item[key] = self._decode_json(item.pop(column))
                result.append(item)
            return result
        finally:
            conn.close()
