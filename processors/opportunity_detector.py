from __future__ import annotations

import re
from typing import Any


class OpportunityDetector:
    """Convert website/business signals into actionable sales opportunities."""

    def detect(
        self,
        *,
        signals: dict[str, bool],
        text: str,
        pages: list[str] | None = None,
        industry: str = "unknown",
    ) -> list[dict[str, Any]]:
        pages = pages or []
        opportunities: list[dict[str, Any]] = []
        normalized = re.sub(r"\s+", " ", text or "").strip().lower()

        def add(kind: str, title: str, description: str, evidence: list[str], score: int, confidence: float) -> None:
            opportunities.append({
                "type": kind,
                "title": title,
                "description": description,
                "evidence": evidence,
                "score": score,
                "confidence": confidence,
                "priority": "high" if score >= 20 else "medium" if score >= 10 else "low",
            })

        if not signals.get("social"):
            add(
                "social_presence",
                "Social Presence Opportunity",
                "No major social-profile signal was detected across the analyzed website content.",
                ["No Facebook, Instagram, LinkedIn, or YouTube signal detected."],
                10,
                0.82,
            )

        if signals.get("booking") and not signals.get("lead_form"):
            add(
                "lead_capture",
                "Lead Capture Opportunity",
                "The website appears to support booking but no clear lead/inquiry form was detected.",
                ["Booking signal detected", "No clear lead-form signal detected"],
                18,
                0.78,
            )

        if signals.get("contact_page") and signals.get("email") and signals.get("phone"):
            add(
                "contact_workflow",
                "Contact Workflow Opportunity",
                "The business has established contact channels, creating a potential opportunity to improve inquiry handling, routing, and follow-up automation.",
                ["Contact page detected", "Email detected", "Phone detected"],
                12,
                0.70,
            )

        if signals.get("reviews") and not signals.get("social"):
            add(
                "reputation_marketing",
                "Reputation Marketing Opportunity",
                "Reviews/testimonials are present while major social-profile signals are absent, suggesting a possible opportunity to repurpose reputation content across channels.",
                ["Reviews/testimonials detected", "No major social-profile signal detected"],
                12,
                0.68,
            )

        if signals.get("services") and len(normalized) < 3000:
            add(
                "website_content",
                "Website Content Opportunity",
                "Services are identified but the available visible content is relatively limited, which may leave room for stronger service-specific conversion content.",
                ["Services signal detected", f"Visible normalized text is approximately {len(normalized)} characters"],
                10,
                0.65,
            )

        if signals.get("booking") or signals.get("lead_form"):
            add(
                "follow_up_automation",
                "Inquiry Follow-up Opportunity",
                "The website has a conversion path that may create appointment or inquiry events suitable for structured follow-up workflows.",
                ["Booking or lead-form conversion path detected"],
                15,
                0.62,
            )

        if industry in {"healthcare", "medical"} and signals.get("booking"):
            add(
                "appointment_automation",
                "Appointment Workflow Opportunity",
                "A healthcare website with booking capability may benefit from appointment reminders, confirmations, routing, and follow-up automation.",
                ["Healthcare/medical industry signal", "Booking signal detected"],
                20,
                0.72,
            )

        return sorted(opportunities, key=lambda item: (-item["score"], item["type"]))
