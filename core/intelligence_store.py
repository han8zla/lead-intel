import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class IntelligenceStore:
    """Persistence boundary for Phase 4 intelligence and audit records."""

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
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    run_id TEXT PRIMARY KEY,
                    lead_id INTEGER NOT NULL,
                    source_url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    summary_json TEXT
                );

                CREATE TABLE IF NOT EXISTS analysis_pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    status TEXT,
                    method TEXT,
                    content_length INTEGER,
                    error_type TEXT,
                    error_message TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS intelligence_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    page_url TEXT,
                    kind TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    confidence REAL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS intelligence_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'DETECTED',
                    confidence REAL,
                    evidence_json TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS unknown_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    page_url TEXT,
                    observation_json TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    interpretation_json TEXT,
                    validation_status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS ai_interpretations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    provider TEXT,
                    model TEXT,
                    input_hash TEXT,
                    status TEXT NOT NULL,
                    confidence REAL,
                    input_summary_json TEXT NOT NULL,
                    output_json TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS intelligence_opportunities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    opportunity_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    priority TEXT,
                    score REAL,
                    confidence REAL,
                    impact REAL,
                    solution_fit REAL,
                    evidence_json TEXT NOT NULL,
                    unknowns_json TEXT NOT NULL,
                    recommendation TEXT,
                    status TEXT NOT NULL DEFAULT 'CANDIDATE',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    lead_id INTEGER NOT NULL,
                    event_name TEXT NOT NULL,
                    stage TEXT,
                    severity TEXT NOT NULL DEFAULT 'INFO',
                    message TEXT,
                    attributes_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id)
                );

                CREATE INDEX IF NOT EXISTS idx_analysis_runs_lead ON analysis_runs(lead_id);
                CREATE INDEX IF NOT EXISTS idx_pages_run ON analysis_pages(run_id);
                CREATE INDEX IF NOT EXISTS idx_observations_run ON intelligence_observations(run_id);
                CREATE INDEX IF NOT EXISTS idx_signals_run ON intelligence_signals(run_id);
                CREATE INDEX IF NOT EXISTS idx_unknowns_run ON unknown_signals(run_id);
                CREATE INDEX IF NOT EXISTS idx_ai_run ON ai_interpretations(run_id);
                CREATE INDEX IF NOT EXISTS idx_opportunities_run ON intelligence_opportunities(run_id);
                CREATE INDEX IF NOT EXISTS idx_audit_run ON audit_events(run_id);
                """
            )
            conn.commit()
        finally:
            conn.close()

    def start_run(self, lead_id: int, source_url: str) -> str:
        run_id = uuid.uuid4().hex
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO analysis_runs (run_id, lead_id, source_url, status, started_at) VALUES (?, ?, ?, 'RUNNING', ?)",
                (run_id, lead_id, source_url, self._now()),
            )
            conn.commit()
        finally:
            conn.close()
        return run_id

    def finish_run(self, run_id: str, status: str, summary: dict | None = None) -> None:
        conn = self._connect()
        try:
            conn.execute("UPDATE analysis_runs SET status = ?, completed_at = ?, summary_json = ? WHERE run_id = ?", (status, self._now(), self._json(summary), run_id))
            conn.commit()
        finally:
            conn.close()

    def fail_run(self, run_id: str, error_type: str, error_message: str) -> None:
        conn = self._connect()
        try:
            conn.execute("UPDATE analysis_runs SET status = 'FAILED', completed_at = ?, error_type = ?, error_message = ? WHERE run_id = ?", (self._now(), error_type, error_message, run_id))
            conn.commit()
        finally:
            conn.close()

    def record_event(self, run_id: str, lead_id: int, event_name: str, *, stage: str | None = None, severity: str = "INFO", message: str | None = None, attributes: dict | None = None, url: str | None = None, status_code: int | None = None) -> int:
        event_attributes = dict(attributes or {})
        if url is not None:
            event_attributes["url"] = url
        if status_code is not None:
            event_attributes["status_code"] = status_code
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT INTO audit_events (run_id, lead_id, event_name, stage, severity, message, attributes_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, lead_id, event_name, stage, severity, message, self._json(event_attributes), self._now()),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def record_page(self, run_id: str, url: str, *, status: str, method: str | None = None, content_length: int | None = None, error_type: str | None = None, error_message: str | None = None, metadata: dict | None = None) -> int:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT INTO analysis_pages (run_id, url, status, method, content_length, error_type, error_message, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, url, status, method, content_length, error_type, error_message, self._json(metadata), self._now()),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def record_observation(self, run_id: str, *, page_url: str | None, kind: str, key: str, value: Any, evidence: dict | list | None = None, confidence: float | None = None) -> int:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT INTO intelligence_observations (run_id, page_url, kind, key, value_json, evidence_json, confidence, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, page_url, kind, key, self._json(value), self._json(evidence), confidence, self._now()),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def record_signal(self, run_id: str, *, name: str, classification: str, confidence: float | None, evidence: list | dict | None = None, context: dict | None = None, status: str = "DETECTED") -> int:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT INTO intelligence_signals (run_id, name, classification, status, confidence, evidence_json, context_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, name, classification, status, confidence, self._json(evidence), self._json(context), self._now()),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def record_unknown(self, run_id: str, *, fingerprint: str, page_url: str | None, observation: dict, context: dict, interpretation: dict | None = None, validation_status: str = "PENDING") -> int:
        now = self._now()
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT INTO unknown_signals (run_id, fingerprint, page_url, observation_json, context_json, interpretation_json, validation_status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, fingerprint, page_url, self._json(observation), self._json(context), self._json(interpretation) if interpretation else None, validation_status, now, now),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def get_unknown(self, unknown_id: int) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM unknown_signals WHERE id = ?", (unknown_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            for key in ("observation_json", "context_json", "interpretation_json"):
                raw = result.get(key)
                result[key.removesuffix("_json")] = json.loads(raw) if raw else None
            return result
        finally:
            conn.close()

    def list_unknowns(self, validation_status: str | None = None, limit: int = 100) -> list[dict]:
        conn = self._connect()
        try:
            if validation_status:
                rows = conn.execute("SELECT * FROM unknown_signals WHERE validation_status = ? ORDER BY updated_at DESC LIMIT ?", (validation_status, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM unknown_signals ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
            results = []
            for row in rows:
                item = dict(row)
                for key in ("observation_json", "context_json", "interpretation_json"):
                    raw = item.get(key)
                    item[key.removesuffix("_json")] = json.loads(raw) if raw else None
                results.append(item)
            return results
        finally:
            conn.close()

    def update_unknown(self, unknown_id: int, *, interpretation: dict | None = None, validation_status: str | None = None) -> bool:
        updates = []
        values: list[Any] = []
        if interpretation is not None:
            updates.append("interpretation_json = ?")
            values.append(self._json(interpretation))
        if validation_status is not None:
            if validation_status not in {"PENDING", "VALIDATED", "REJECTED", "KEPT_UNKNOWN"}:
                raise ValueError("Invalid unknown signal validation status")
            updates.append("validation_status = ?")
            values.append(validation_status)
        if not updates:
            return False
        updates.append("updated_at = ?")
        values.append(self._now())
        values.append(unknown_id)
        conn = self._connect()
        try:
            cursor = conn.execute(f"UPDATE unknown_signals SET {', '.join(updates)} WHERE id = ?", values)
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def record_ai(self, run_id: str, *, purpose: str, provider: str | None, model: str | None, input_hash: str | None, status: str, input_summary: dict, output: dict | None = None, confidence: float | None = None, error_message: str | None = None) -> int:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT INTO ai_interpretations (run_id, purpose, provider, model, input_hash, status, confidence, input_summary_json, output_json, error_message, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, purpose, provider, model, input_hash, status, confidence, self._json(input_summary), self._json(output) if output else None, error_message, self._now()),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def record_opportunity(self, run_id: str, opportunity: dict, status: str = "CANDIDATE") -> int:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT INTO intelligence_opportunities (run_id, opportunity_type, title, priority, score, confidence, impact, solution_fit, evidence_json, unknowns_json, recommendation, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, opportunity.get("type", "unknown"), opportunity.get("title", "Untitled opportunity"), opportunity.get("priority"), opportunity.get("score"), opportunity.get("confidence"), opportunity.get("impact"), opportunity.get("solution_fit"), self._json(opportunity.get("evidence", [])), self._json(opportunity.get("unknowns", [])), opportunity.get("recommendation"), status, self._now()),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()
