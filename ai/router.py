from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from .providers import AIProviderError, AIResponse, OpenAICompatibleProvider, providers_from_env

logger = logging.getLogger(__name__)


@dataclass
class ProviderState:
    provider: OpenAICompatibleProvider
    cooldown_until: float = 0.0


class AIRouter:
    """Route generation through a provider/model pool with automatic failover."""

    COOLDOWN_SECONDS = 60.0

    def __init__(self, providers: list[OpenAICompatibleProvider] | None = None):
        if providers is None:
            providers = self._providers_from_env()
        self.providers = [ProviderState(provider) for provider in providers]

    @staticmethod
    def _providers_from_env() -> list[OpenAICompatibleProvider]:
        providers: list[OpenAICompatibleProvider] = []
        providers.extend(providers_from_env("GROQ", default_base_url="https://api.groq.com/openai/v1"))
        providers.extend(providers_from_env("OPENROUTER", default_base_url="https://openrouter.ai/api/v1"))
        return providers

    @property
    def available(self) -> bool:
        return bool(self.providers)

    def provider_names(self) -> list[str]:
        return [state.provider.config.name for state in self.providers]

    def models(self) -> list[str]:
        return [state.provider.config.model for state in self.providers]

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
                "No AI providers configured. Set GROQ_API_KEY/GROQ_MODELS or another provider."
            )

        last_error: AIProviderError | None = None
        available_states = self._ordered_available()
        if not available_states:
            raise AIProviderError("All configured AI models are temporarily cooling down", retryable=True)

        for state in available_states:
            try:
                response = await state.provider.generate(
                    system=system,
                    user=user,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                state.cooldown_until = 0.0
                logger.info("AI generation succeeded with %s / %s", response.provider, response.model)
                return response
            except AIProviderError as exc:
                last_error = exc
                if exc.retryable:
                    state.cooldown_until = time.monotonic() + self.COOLDOWN_SECONDS
                logger.warning(
                    "AI provider/model %s failed (retryable=%s, status=%s); trying next model/provider",
                    state.provider.config.name,
                    exc.retryable,
                    exc.status_code,
                )

        raise last_error or AIProviderError("All configured AI models/providers failed")

    def _ordered_available(self) -> list[ProviderState]:
        now = time.monotonic()
        return [state for state in self.providers if state.cooldown_until <= now]
