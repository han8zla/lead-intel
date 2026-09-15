from __future__ import annotations

import json
from typing import Any

from .providers import AIResponse
from .router import AIRouter


class AIBusinessAnalyst:
    """Use an AI provider to validate opportunity candidates without executing actions."""

    def __init__(self, router: AIRouter | None = None):
        self.router = router or AIRouter()
        self.last_response: AIResponse | None = None

    async def analyze(self, *, analysis: dict[str, Any]) -> dict[str, Any]:
        evidence = self._compact_payload(analysis)
        system = (
            "You are a business process analyst reviewing website intelligence. "
            "Use only the supplied evidence. Do not invent hidden systems, staff, "
            "workflows, pain points, metrics, customers, integrations, or technology. "
            "A website feature proves that a capability exists, not that its backend "
            "process is manual or broken. Treat unknowns as unknowns. "
            "Return ONLY valid JSON matching this schema: "
            '{"overall_assessment":"strong|moderate|weak|insufficient",'
            '"reason":"string",'
            '"opportunity_reviews":[{"type":"string","keep":true,'
            '"confidence":"high|medium|low","reason":"string",'
            '"missing_evidence":["string"],"recommended_next_step":"string"}],'
            '"additional_observations":["string"]}'
        )
        user = (
            "Review the following compact, evidence-grounded business intelligence. "
            "Validate whether each candidate is worth presenting to a human reviewer. "
            "Do not calculate or replace the deterministic priority score. "
            "If evidence is insufficient, say so rather than guessing.\n\n"
            + json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
        )

        response = await self.router.generate(
            system=system,
            user=user,
            temperature=0.1,
            max_tokens=1200,
        )
        self.last_response = response
        result = self._parse_json(response.text)
        result["provider"] = response.provider
        result["model"] = response.model
        return result

    @staticmethod
    def _compact_payload(analysis: dict[str, Any]) -> dict[str, Any]:
        return {
            "business": {
                "name": analysis.get("business_name"),
                "industry": analysis.get("industry"),
                "services": analysis.get("services", []),
                "website": analysis.get("url"),
            },
            "business_intelligence": analysis.get("business_intelligence", {}),
            "signals": analysis.get("signals", {}),
            "opportunities": [
                {
                    "type": item.get("type"),
                    "title": item.get("title"),
                    "score": item.get("score"),
                    "impact": item.get("impact"),
                    "confidence": item.get("confidence"),
                    "solution_fit": item.get("solution_fit"),
                    "evidence": item.get("evidence", []),
                    "unknowns": item.get("unknowns", []),
                    "recommendation": item.get("recommendation"),
                }
                for item in analysis.get("opportunities", [])
            ],
        }

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        candidate = text.strip()
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            if lines and lines[0].strip().lower() == "```json":
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            candidate = "\n".join(lines).strip()
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise ValueError("AI business analyst returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("AI business analyst returned a non-object JSON response")

        assessment = parsed.get("overall_assessment")
        if assessment not in {"strong", "moderate", "weak", "insufficient"}:
            raise ValueError("AI business analyst returned an invalid overall_assessment")
        reviews = parsed.get("opportunity_reviews", [])
        if not isinstance(reviews, list):
            raise ValueError("AI business analyst returned invalid opportunity_reviews")
        return parsed
