from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .providers import OpenAICompatibleProvider, ProviderConfig


@dataclass(frozen=True)
class RegisteredProvider:
    id: int
    name: str
    base_url: str
    enabled: bool
    models: tuple[str, ...]


class AIProviderRegistry:
    """Persistent registry for user-configured OpenAI-compatible AI endpoints."""

    def __init__(self, db_path: str = "./data/lead_intelligence.db"):
        self.db_path = db_path

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _fernet() -> Fernet:
        secret = os.getenv("AI_SETTINGS_ENCRYPTION_KEY", "").strip()
        if not secret:
            raise RuntimeError(
                "AI_SETTINGS_ENCRYPTION_KEY is required to store AI provider credentials"
            )
        try:
            return Fernet(secret.encode("ascii"))
        except Exception as exc:
            raise RuntimeError("AI_SETTINGS_ENCRYPTION_KEY must be a valid Fernet key") from exc

    def setup_tables(self) -> None:
        conn = self._connect()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                base_url TEXT NOT NULL,
                api_key_encrypted TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                timeout REAL NOT NULL DEFAULT 45.0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id INTEGER NOT NULL,
                model_name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                priority INTEGER NOT NULL DEFAULT 100,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(provider_id, model_name),
                FOREIGN KEY(provider_id) REFERENCES ai_providers(id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()
        conn.close()

    def upsert_provider(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        models: list[str] | None = None,
        enabled: bool = True,
        timeout: float = 45.0,
    ) -> int:
        self.setup_tables()
        name = name.strip()
        base_url = base_url.rstrip("/").strip()
        api_key = api_key.strip()
        if not name or not base_url or not api_key:
            raise ValueError("Provider name, base URL, and API key are required")
        encrypted = self._fernet().encrypt(api_key.encode("utf-8")).decode("ascii")
        normalized_models = []
        for model in models or []:
            model = str(model).strip()
            if model and model not in normalized_models:
                normalized_models.append(model)

        conn = self._connect()
        existing = conn.execute("SELECT id FROM ai_providers WHERE name = ?", (name,)).fetchone()
        if existing:
            provider_id = existing["id"]
            conn.execute(
                """UPDATE ai_providers
                   SET base_url = ?, api_key_encrypted = ?, enabled = ?, timeout = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (base_url, encrypted, int(enabled), timeout, provider_id),
            )
        else:
            cursor = conn.execute(
                """INSERT INTO ai_providers (name, base_url, api_key_encrypted, enabled, timeout)
                   VALUES (?, ?, ?, ?, ?)""",
                (name, base_url, encrypted, int(enabled), timeout),
            )
            provider_id = cursor.lastrowid

        if models is not None:
            conn.execute("DELETE FROM ai_models WHERE provider_id = ?", (provider_id,))
            for priority, model in enumerate(normalized_models, start=1):
                conn.execute(
                    """INSERT INTO ai_models (provider_id, model_name, enabled, priority)
                       VALUES (?, ?, 1, ?)""",
                    (provider_id, model, priority),
                )
        conn.commit()
        conn.close()
        return int(provider_id)

    def delete_provider(self, provider_id: int) -> bool:
        self.setup_tables()
        conn = self._connect()
        cursor = conn.execute("DELETE FROM ai_providers WHERE id = ?", (provider_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted

    def set_provider_enabled(self, provider_id: int, enabled: bool) -> bool:
        self.setup_tables()
        conn = self._connect()
        cursor = conn.execute(
            "UPDATE ai_providers SET enabled = ?, updated_at = datetime('now') WHERE id = ?",
            (int(enabled), provider_id),
        )
        conn.commit()
        updated = cursor.rowcount > 0
        conn.close()
        return updated

    def list_providers(self) -> list[RegisteredProvider]:
        self.setup_tables()
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT p.id, p.name, p.base_url, p.enabled,
                   m.model_name, m.enabled AS model_enabled, m.priority
            FROM ai_providers p
            LEFT JOIN ai_models m ON m.provider_id = p.id
            ORDER BY p.name, m.priority, m.id
            """
        ).fetchall()
        conn.close()
        grouped: dict[int, dict[str, Any]] = {}
        for row in rows:
            item = grouped.setdefault(
                row["id"],
                {
                    "id": row["id"],
                    "name": row["name"],
                    "base_url": row["base_url"],
                    "enabled": bool(row["enabled"]),
                    "models": [],
                },
            )
            if row["model_name"] and row["model_enabled"]:
                item["models"].append(row["model_name"])
        return [
            RegisteredProvider(
                id=item["id"],
                name=item["name"],
                base_url=item["base_url"],
                enabled=item["enabled"],
                models=tuple(item["models"]),
            )
            for item in grouped.values()
        ]

    def _credentials(self, provider_id: int) -> tuple[str, str, float] | None:
        self.setup_tables()
        conn = self._connect()
        row = conn.execute(
            "SELECT base_url, api_key_encrypted, timeout FROM ai_providers WHERE id = ? AND enabled = 1",
            (provider_id,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        try:
            key = self._fernet().decrypt(row["api_key_encrypted"].encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError("Stored AI provider credentials cannot be decrypted") from exc
        return row["base_url"], key, float(row["timeout"])

    def build_providers(self) -> list[OpenAICompatibleProvider]:
        self.setup_tables()
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT p.id, p.name, p.base_url, p.api_key_encrypted, p.timeout,
                   m.model_name, m.priority
            FROM ai_providers p
            JOIN ai_models m ON m.provider_id = p.id AND m.enabled = 1
            WHERE p.enabled = 1
            ORDER BY m.priority, p.id, m.id
            """
        ).fetchall()
        conn.close()
        if not rows:
            return []

        fernet = self._fernet()
        providers = []
        decrypted: dict[int, str] = {}
        for row in rows:
            provider_id = row["id"]
            if provider_id not in decrypted:
                try:
                    decrypted[provider_id] = fernet.decrypt(
                        row["api_key_encrypted"].encode("ascii")
                    ).decode("utf-8")
                except InvalidToken as exc:
                    raise RuntimeError(
                        f"Stored credentials for provider '{row['name']}' cannot be decrypted"
                    ) from exc
            providers.append(
                OpenAICompatibleProvider(
                    ProviderConfig(
                        name=f"{row['name']}:{row['model_name']}",
                        base_url=row["base_url"],
                        api_key=decrypted[provider_id],
                        model=row["model_name"],
                        timeout=float(row["timeout"]),
                    )
                )
            )
        return providers

    @staticmethod
    def discover_models(*, base_url: str, api_key: str, timeout: float = 15.0) -> list[str]:
        """Discover model IDs from an OpenAI-compatible GET /models endpoint."""
        endpoint = base_url.rstrip("/") + "/models"
        request = urllib.request.Request(
            endpoint,
            headers={"Authorization": f"Bearer {api_key.strip()}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Provider returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Provider connection failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Provider returned invalid JSON from /models") from exc

        data = payload.get("data", [])
        if not isinstance(data, list):
            raise RuntimeError("Provider /models response did not contain a data list")
        models = []
        for item in data:
            if isinstance(item, dict) and item.get("id"):
                model = str(item["id"]).strip()
                if model and model not in models:
                    models.append(model)
        return models

    def public_provider(self, provider_id: int) -> dict[str, Any] | None:
        for provider in self.list_providers():
            if provider.id == provider_id:
                return {
                    "id": provider.id,
                    "name": provider.name,
                    "base_url": provider.base_url,
                    "enabled": provider.enabled,
                    "models": list(provider.models),
                }
        return None
