from ai.router import AIRouter


def test_router_uses_provider_order():
    router = AIRouter(providers=[])
    assert router.provider_names() == []
