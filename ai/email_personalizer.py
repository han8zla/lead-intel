from __future__ import annotations

import json
from typing import Any

from .providers import AIResponse
from .router import AIRouter


class EmailPersonalizer:
    """Generate concise, evidence-grounded cold outreach from lead intelligence."""

    def __init__(self, router: AIRouter | None = None):
        self.router = router or AIRouter()
        self.last_response: AIResponse | None = None

    async def generate(
        self,
        *,
        analysis: dict[str, Any],
        sender_name: str = "",
        sender_company: str = "",
    ) -> str:
        evidence = {
            "business_name": analysis.get("business_name"),
            "industry": analysis.get("industry"),
            "services": analysis.get("services", []),
            "opportunity_score": analysis.get("opportunity_score", 0),
            "top_opportunities": analysis.get("opportunities", [])[:3],
            "signals": analysis.get("signals", {}),
            "signal_evidence": analysis.get("signal_evidence", {}),
            "website": analysis.get("url"),
        }

        system = (
            "You write concise B2B cold emails. Use only evidence supplied in the lead intelligence. "
            "Never invent facts, customers, metrics, integrations, pain points, or personal details. "
            "Do not mention hidden scoring logic. Pick one strongest opportunity and explain it simply. "
            "The email should feel manually researched, not mass-generated. "
            "Avoid sensitive personal information and avoid implying access to private systems. "
            "Return exactly: SUBJECT: ...\\n\\nBODY:\\n..."
        )
        user = (
            "Create one personalized outreach email from this verified website intelligence. "
            "Keep the body under 140 words, use a soft CTA, and make the proposed automation concrete.\n\n"
            f"Sender: {sender_name or 'Our team'} | Company: {sender_company or 'Our company'}\n"
            f"Lead intelligence:\n{json.dumps(evidence, ensure_ascii=False, indent=2)}"
        )

        response = await self.router.generate(
            system=system,
            user=user,
            temperature=0.45,
            max_tokens=500,
        )
        self.last_response = response
        return response.text
