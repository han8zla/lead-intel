import pytest

from ai.providers import AIResponse
from ai.unknown_signal_interpreter import UnknownSignalInterpreter


class FakeRouter:
    available = True

    def __init__(self, text):
        self.text = text

    async def generate(self, **kwargs):
        return AIResponse(provider="fake", model="test-model", text=self.text)


@pytest.mark.asyncio
async def test_unknown_signal_interpreter_preserves_uncertainty():
    router = FakeRouter(
        '{"classification":"ambiguous","canonical_name":"Assessment Widget",'
        '"confidence":"medium","business_meaning":"May indicate an interactive assessment entry point.",'
        '"evidence_needed":["Confirm what happens after submission."],'
        '"recommended_action":"promote_after_validation"}'
    )
    interpreter = UnknownSignalInterpreter(router=router)

    result = await interpreter.interpret(
        observation={"text": "Start assessment", "element": "button"},
        context={"page": "/new-patients/", "audience": "patients"},
    )

    assert result["classification"] == "ambiguous"
    assert result["confidence"] == "medium"
    assert result["recommended_action"] == "promote_after_validation"
    assert result["provider"] == "fake"
    assert result["model"] == "test-model"


def test_unknown_signal_interpreter_rejects_invalid_contract():
    with pytest.raises(ValueError, match="invalid classification"):
        UnknownSignalInterpreter._parse_json(
            '{"classification":"fact","canonical_name":"x",'
            '"confidence":"high","business_meaning":"x",'
            '"evidence_needed":[],"recommended_action":"preserve"}'
        )
