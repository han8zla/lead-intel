from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from .provider_registry import AIProviderRegistry
from .providers import AIProviderError, AIResponse, OpenAICompatibleProvider, providers_from_env

logger = logging.getLogger(__name__)


@dataclass
class ProviderState:
    provider: OpenAICompatibleProvider
    cooldown_until: float = 0.0


class AIRouter:
    """Route generation through dynamic providers with automatic failover."""

    COOLDOWN_SECONDS = 60.0

    def __init__(
        self,
        providers: list[OpenAICompatibleProvider] | None = None,
        registry: AIProviderRegistry | None = None,
    ):
        self.registry = registry
        if providers is None:
            providers = self._providers_from_registry_or_env()
        self.providers = [ProviderState(provider) for provider in providers]

    def _providers_from_registry_or_env(self) -> list[OpenAICompatibleProvider]:
        if self.registry is not None:
            registered = self.registry.build_providers()
            if registered:
                return registered
        return self._providers_from_env()

    @staticmethod
    def _providers_from_env() -> list[OpenAICompatibleProvider]:
        """Backward-compatible environment configuration."""
        providers: list[OpenAICompatibleProvider] = []
        providers.extend(providers_from_env("GROQ", default_base_url="https://api.groq.com/openai/v1"))
        providers.extend(providers_from_env("OPENROUTER", default_base_url="https://openrouter.ai/api/v1"))
        providers.extend(providers_from_env("GEMINI", default_base_url="https://generativelanguage.googleapis.com/v1beta/openai/"))
        return providers

    def refresh(self) -> None:
        """Reload provider configuration while preserving active cooldowns."""
        if self.registry is None:
            return
        current = {state.provider.config.name: state.cooldown_until for state in self.providers}
        providers = self.registry.build_providers()
        if not providers:
            providers = self._providers_from_env()
        self.providers = [
            ProviderState(provider, cooldown_until=current.get(provider.config.name, 0.0))
            for provider in providers
        ]

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
        self.refresh()
        if not self.providers:
            raise AIProviderError(
                "No AI providers configured. Add a provider in AI Settings or configure the environment."
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
        states = [state for state in self.providers if state.cooldown_until <= now]
        if self.registry is None:
            return states

        routing = self.registry.get_routing_config()
        if routing.mode != "manual":
            return states

        # ProviderState names intentionally remain human-readable as
        # "Provider Name:model". Resolve the configured numeric provider ID
        # through the registry rather than comparing the ID directly to that
        # display name.
        provider_names = {
            provider.id: provider.name
            for provider in self.registry.list_providers()
        }
        provider_name = provider_names.get(routing.active_provider_id)
        if not provider_name or not routing.active_model:
            return states

        target = f"{provider_name}:{routing.active_model}"
        selected = [
            state for state in states
            if state.provider.config.name == target
        ]
        remaining = [
            state for state in states
            if state.provider.config.name != target
        ]
        return selected + remaining
