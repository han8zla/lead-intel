import pytest

from ai.business_analyst import AIBusinessAnalyst
from ai.providers import AIResponse


class FakeRouter:
    available = True

    def __init__(self, response):
        self.response = response
        self.last_user = ""

    async def generate(self, *, system, user, temperature, max_tokens):
        self.last_user = user
        return AIResponse(text=self.response, provider="test-provider", model="test-model")


@pytest.mark.asyncio
async def test_business_analyst_returns_validated_json_without_replacing_score():
    router = FakeRouter(
        '{"overall_assessment":"strong",'
        '"reason":"The appointment workflow is visible and commercially relevant.",'
        '"opportunity_reviews":[{"type":"appointment_lifecycle","keep":true,'
        '"confidence":"high","reason":"Booking is directly evidenced.",'
        '"missing_evidence":["Reminder integration is unknown"],'
        '"recommended_next_step":"Audit reminder and rescheduling workflow."}],'
        '"additional_observations":[]}'
    )
    analyst = AIBusinessAnalyst(router=router)
    analysis = {
        "business_name": "Example Clinic",
        "industry": "healthcare",
        "services": ["primary care"],
        "url": "https://example.com",
        "signals": {"booking": True, "lead_form": False},
        "business_intelligence": {"unknowns": ["Reminder workflow is not visible"]},
        "opportunity_score": 91,
        "opportunities": [
            {
                "type": "appointment_lifecycle",
                "title": "Appointment Lifecycle Automation",
                "score": 91,
                "impact": 90,
                "confidence": 82,
                "solution_fit": 92,
                "evidence": ["Online appointment capability is visible"],
                "unknowns": ["Reminder automation is unknown"],
                "recommendation": "Audit appointment lifecycle workflows.",
            }
        ],
    }

    result = await analyst.analyze(analysis=analysis)

    assert result["overall_assessment"] == "strong"
    assert result["opportunity_reviews"][0]["keep"] is True
    assert result["provider"] == "test-provider"
    assert result["model"] == "test-model"
    assert analysis["opportunity_score"] == 91
    assert "Example Clinic" in router.last_user
    assert "91" in router.last_user


def test_business_analyst_rejects_invalid_json():
    with pytest.raises(ValueError, match="invalid JSON"):
        AIBusinessAnalyst._parse_json("not-json")


def test_business_analyst_rejects_invalid_assessment():
    with pytest.raises(ValueError, match="invalid overall_assessment"):
        AIBusinessAnalyst._parse_json('{"overall_assessment":"maybe"}')
