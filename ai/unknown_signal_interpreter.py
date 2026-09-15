from __future__ import annotations

import json
from typing import Any

from .providers import AIResponse
from .router import AIRouter


class UnknownSignalInterpreter:
    """Interpret ambiguous observations without turning them into facts automatically."""

    def __init__(self, router: AIRouter | None = None):
        self.router = router or AIRouter()
        self.last_response: AIResponse | None = None

    async def interpret(self, *, observation: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        system = (
            "You are an evidence analyst for website intelligence. Use only the supplied "
            "observation and context. Do not invent hidden workflows, systems, staff, "
            "pain points, metrics, customers, integrations, or outcomes. "
            "Return ONLY valid JSON matching this schema: "
            '{"classification":"known_candidate|ambiguous|insufficient",'
            '"canonical_name":"string",'
            '"confidence":"high|medium|low",'
            '"business_meaning":"string",'
            '"evidence_needed":["string"],'
            '"recommended_action":"preserve|promote_after_validation|ignore"}'
        )
        user = (
            "Interpret this unknown observation conservatively. A plausible interpretation "
            "is not proof. Prefer ambiguous or insufficient when evidence does not support "
            "a reusable signal.\n\n"
            + json.dumps(
                {"observation": observation, "context": context},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        response = await self.router.generate(
            system=system,
            user=user,
            temperature=0.0,
            max_tokens=500,
        )
        self.last_response = response
        result = self._parse_json(response.text)
        result["provider"] = response.provider
        result["model"] = response.model
        return result

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
            raise ValueError("AI unknown signal interpreter returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("AI unknown signal interpreter returned a non-object JSON response")
        if parsed.get("classification") not in {"known_candidate", "ambiguous", "insufficient"}:
            raise ValueError("AI unknown signal interpreter returned invalid classification")
        if parsed.get("confidence") not in {"high", "medium", "low"}:
            raise ValueError("AI unknown signal interpreter returned invalid confidence")
        if parsed.get("recommended_action") not in {"preserve", "promote_after_validation", "ignore"}:
            raise ValueError("AI unknown signal interpreter returned invalid recommended_action")
        if not isinstance(parsed.get("evidence_needed", []), list):
            raise ValueError("AI unknown signal interpreter returned invalid evidence_needed")
        return parsed
