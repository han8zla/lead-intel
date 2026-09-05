from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass


class AIProviderError(RuntimeError):
    """An AI provider could not complete a request."""

    def __init__(self, message: str, *, retryable: bool = False, status_code: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


@dataclass(frozen=True)
class AIResponse:
    text: str
    provider: str
    model: str


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    model: str
    timeout: float = 45.0


class OpenAICompatibleProvider:
    """Dependency-free adapter for OpenAI-compatible chat APIs."""

    def __init__(self, config: ProviderConfig):
        self.config = config

    async def generate(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.4,
        max_tokens: int = 800,
    ) -> AIResponse:
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        body = json.dumps(payload).encode("utf-8")
        endpoint = self.config.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = await asyncio.to_thread(self._request, endpoint, body, headers)
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError(f"{self.config.name} request failed: {exc}", retryable=True) from exc

        try:
            data = json.loads(response)
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise AIProviderError(f"{self.config.name} returned an unexpected response", retryable=False) from exc

        return AIResponse(text=str(text).strip(), provider=self.config.name, model=self.config.model)

    def _request(self, endpoint: str, body: bytes, headers: dict[str, str]) -> str:
        request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or exc.code >= 500
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            raise AIProviderError(
                f"{self.config.name} HTTP {exc.code}: {detail}",
                retryable=retryable,
                status_code=exc.code,
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise AIProviderError(f"{self.config.name} network/timeout error: {exc}", retryable=True) from exc


def _base_provider_config(prefix: str, *, default_base_url: str = "") -> tuple[str, str, float] | None:
    api_key = os.getenv(f"{prefix}_API_KEY", "").strip()
    if not api_key:
        return None
    base_url = os.getenv(f"{prefix}_BASE_URL", default_base_url).strip()
    if not base_url:
        raise ValueError(f"{prefix}_BASE_URL is required for provider {prefix}")
    try:
        timeout = float(os.getenv(f"{prefix}_TIMEOUT", "45"))
    except ValueError:
        timeout = 45.0
    return api_key, base_url, timeout


def provider_from_env(prefix: str, *, default_base_url: str = "") -> OpenAICompatibleProvider | None:
    """Build one provider using the first configured model.

    For model failover, prefer ``providers_from_env``. ``<PREFIX>_MODEL`` is
    retained for backward compatibility with existing installations.
    """
    providers = providers_from_env(prefix, default_base_url=default_base_url)
    return providers[0] if providers else None


def providers_from_env(prefix: str, *, default_base_url: str = "") -> list[OpenAICompatibleProvider]:
    """Build a provider pool from comma-separated model configuration.

    ``<PREFIX>_MODELS`` accepts an ordered comma-separated list. The older
    singular ``<PREFIX>_MODEL`` remains supported and becomes a one-model pool.
    """
    config = _base_provider_config(prefix, default_base_url=default_base_url)
    if config is None:
        return []
    api_key, base_url, timeout = config
    raw_models = os.getenv(f"{prefix}_MODELS", "").strip()
    if not raw_models:
        raw_models = os.getenv(f"{prefix}_MODEL", "").strip()
    models = []
    for model in raw_models.split(","):
        model = model.strip()
        if model and model not in models:
            models.append(model)
    return [
        OpenAICompatibleProvider(
            ProviderConfig(
                name=f"{prefix.lower()}:{model}",
                base_url=base_url,
                api_key=api_key,
                model=model,
                timeout=timeout,
            )
        )
        for model in models
    ]
