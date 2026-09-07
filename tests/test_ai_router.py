import asyncio

from ai.providers import AIProviderError, AIResponse, ProviderConfig
from ai.router import AIRouter


class FakeProvider:
    def __init__(self, name, model, response=None, error=None):
        self.config = ProviderConfig(name=name, base_url="https://example.invalid", api_key="test", model=model)
        self.response = response
        self.error = error
        self.calls = 0

    async def generate(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response


def test_router_uses_provider_order():
    router = AIRouter(providers=[])
    assert router.provider_names() == []


def test_router_fails_over_to_next_model_on_rate_limit():
    first = FakeProvider(
        "groq:one",
        "model-one",
        error=AIProviderError("rate limited", retryable=True, status_code=429),
    )
    second = FakeProvider(
        "groq:two",
        "model-two",
        response=AIResponse("ok", "groq:two", "model-two"),
    )
    router = AIRouter(providers=[first, second])

    result = asyncio.run(router.generate(system="system", user="user"))

    assert result.model == "model-two"
    assert first.calls == 1
    assert second.calls == 1
    assert router.providers[0].cooldown_until > 0
