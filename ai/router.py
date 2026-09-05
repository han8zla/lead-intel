from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from .providers import AIProviderError, AIResponse, OpenAICompatibleProvider, provider_from_env

logger = logging.getLogger(__name__)


@dataclass
class ProviderState:
    provider: OpenAICompatibleProvider
    cooldown_until: float = 0.0


class AIRouter:
    """Route generation through configured providers with automatic failover."""

    def __init__(self, providers: list[OpenAICompatibleProvider] | None = None):
        if providers is None:
            providers = self._providers_from_env()
        self.providers = [ProviderState(provider) for provider in providers]
        self._lock = asyncio.Lock()

    @staticmethod
    def _providers_from_env() -> list[OpenAICompatibleProvider]:
        providers: list[OpenAICompatibleProvider] = []

        groq = provider_from_env(
            "GROQ",
            default_base_url="https://api.groq.com/openai/v1",
        )
        if groq:
            providers.append(groq)

        # Optional fallback. This works with OpenRouter and other compatible
        # gateways without changing the rest of the application.
        openrouter = provider_from_env(
            "OPENROUTER",
            default_base_url="https://openrouter.ai/api/v1",
        )
        if openrouter:
            providers.append(openrouter)

        return providers

    @property
    def available(self) -> bool:
        return bool(self.providers)

    async def generate(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.4,
        max_tokens: int = 800,
    ) -> AIResponse:
        if not self.providers:
            raise AIProviderError(
                "No AI providers configured. Set GROQ_API_KEY/GROQ_MODEL or another provider."
            )

        last_error: AIProviderError | None = None
        for state in self._ordered_available():
            try:
                response = await state.provider.generate(
                    system=system,
                    user=user,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                state.cooldown_until = 0.0
                return response
            except AIProviderError as exc:
                last_error = exc
                if exc.retryable:
                    # A 429/5xx should temporarily remove this provider from
                    # rotation so the next configured provider gets a chance.
                    state.cooldown_until = time.monotonic() + 60.0
                logger.warning(
                    "AI provider %s failed (retryable=%s, status=%s); trying next provider",
                    state.provider.config.name,
                    exc.retryable,
                    exc.status_code,
                )

        raise last_error or AIProviderError("All AI providers failed")

    def _ordered_available(self) -> list[ProviderState]:
        now = time.monotonic()
        available = [state for state in self.providers if state.cooldown_until <= now]
        cooling = [state for state in self.providers if state.cooldown_until > now]
        return available + cooling
