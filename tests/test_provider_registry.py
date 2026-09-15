import os
import sqlite3

from cryptography.fernet import Fernet

from ai.provider_registry import AIProviderRegistry
from ai.router import AIRouter


def test_registry_stores_credentials_encrypted_and_builds_models(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    registry = AIProviderRegistry(str(tmp_path / "ai.db"))

    provider_id = registry.upsert_provider(
        name="Test Provider",
        base_url="https://example.com/v1",
        api_key="secret-key",
        models=["model-a", "model-b", "model-a"],
    )

    providers = registry.list_providers()
    assert providers[0].id == provider_id
    assert providers[0].models == ("model-a", "model-b")

    conn = sqlite3.connect(tmp_path / "ai.db")
    stored = conn.execute("SELECT api_key_encrypted FROM ai_providers").fetchone()[0]
    conn.close()
    assert stored != "secret-key"
    assert len(registry.build_providers()) == 2
    assert registry.build_providers()[0].config.api_key == "secret-key"


def test_router_refreshes_from_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_SETTINGS_ENCRYPTION_KEY", os.environ.get("AI_SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode()))
    registry = AIProviderRegistry(str(tmp_path / "ai.db"))
    registry.upsert_provider(
        name="Test Provider",
        base_url="https://example.com/v1",
        api_key="secret-key",
        models=["model-a"],
    )

    router = AIRouter(registry=registry)
    assert router.models() == ["model-a"]

    registry.upsert_provider(
        name="Test Provider",
        base_url="https://example.com/v1",
        api_key="secret-key",
        models=["model-b"],
    )
    router.refresh()
    assert router.models() == ["model-b"]
