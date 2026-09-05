from __future__ import annotations

import re
from typing import Any


class OpportunityDetector:
    """Turn website evidence into distinct, sales-relevant opportunities."""

    def detect(
        self,
        *,
        signals: dict[str, bool],
        text: str,
        pages: list[str] | None = None,
        industry: str = "unknown",
    ) -> list[dict[str, Any]]:
        pages = pages or []
        normalized = re.sub(r"\s+", " ", text or "").strip().lower()
        opportunities: list[dict[str, Any]] = []

        def add(
            kind: str,
            title: str,
            description: str,
            evidence: list[str],
            impact: int,
            confidence: float,
        ) -> None:
            evidence = [item for item in evidence if item]
            evidence_factor = min(1.0, 0.65 + (0.10 * max(0, len(evidence) - 1)))
            score = round(impact * confidence * evidence_factor)
            opportunities.append(
                {
                    "type": kind,
                    "title": title,
                    "description": description,
                    "evidence": evidence,
                    "score": max(1, min(100, score)),
                    "confidence": round(confidence, 2),
                    "impact": impact,
                    "priority": "high" if score >= 60 else "medium" if score >= 35 else "low",
                }
            )

        # Booking is an appointment/conversion workflow, not a lead-capture
        # opportunity. Keeping these rules separate prevents duplicate sales ideas.
        if signals.get("booking"):
            booking_evidence = ["Appointment/booking capability detected"]
            if signals.get("phone") or signals.get("email"):
                booking_evidence.append("Direct contact channel detected")
            if industry in {"healthcare", "medical"}:
                booking_evidence.append("Healthcare/medical industry detected")
                add(
                    "appointment_follow_up",
                    "Appointment Follow-up Automation",
                    "The website can receive appointments, creating a concrete opportunity for confirmations, reminders, no-show recovery, and post-appointment follow-up.",
                    booking_evidence,
                    impact=95,
                    confidence=0.90,
                )
            else:
                add(
                    "appointment_follow_up",
                    "Appointment Follow-up Automation",
                    "The website can receive appointments, creating a potential workflow for confirmations, reminders, rescheduling, and follow-up.",
                    booking_evidence,
                    impact=88,
                    confidence=0.86,
                )

        # A form is evidence of lead capture already existing. We do not call
        # the form itself an opportunity. The opportunity is what can happen
        # after submission: routing, qualification and follow-up.
        if signals.get("lead_form"):
            form_evidence = ["Lead/inquiry form detected"]
            if signals.get("email"):
                form_evidence.append("Email channel detected")
            if signals.get("phone"):
                form_evidence.append("Phone channel detected")
            if not signals.get("booking"):
                add(
                    "inquiry_follow_up",
                    "Inquiry Follow-up Automation",
                    "The website already captures inquiries, creating an opportunity to automatically acknowledge, qualify, route, and follow up with new submissions.",
                    form_evidence,
                    impact=82,
                    confidence=0.88,
                )
            else:
                add(
                    "lead_routing",
                    "Lead Routing & Qualification",
                    "The website has both appointment and inquiry conversion paths, creating an opportunity to route and qualify requests before they reach staff.",
                    form_evidence + ["Booking capability also detected"],
                    impact=78,
                    confidence=0.82,
                )
        elif signals.get("contact_page") and not signals.get("booking"):
            add(
                "lead_capture",
                "Lead Capture / Inquiry Workflow",
                "A contact path exists, but no dedicated inquiry form was confidently detected. A structured inquiry workflow could make it easier to capture, qualify, and route prospects.",
                ["Contact page detected", "No dedicated lead/inquiry form detected"],
                impact=72,
                confidence=0.78,
            )

        # Contact workflow is only raised when there is a real routing gap;
        # having an email and phone number alone is not treated as a problem.
        if signals.get("contact_page") and signals.get("email") and signals.get("phone") and not signals.get("lead_form") and not signals.get("booking"):
            add(
                "contact_routing",
                "Contact Routing & Response Workflow",
                "Multiple contact channels are available, but there is no detected structured conversion path. Centralized routing and response automation could reduce manual handling.",
                [
                    "Contact page detected",
                    "Email detected",
                    "Phone detected",
                    "No booking or lead form detected",
                ],
                impact=68,
                confidence=0.76,
            )

        # Website conversion opportunity: only flag it when there is something
        # meaningful to convert (services) and the site lacks a clear CTA path.
        if signals.get("services") and not signals.get("booking") and not signals.get("lead_form"):
            add(
                "website_conversion",
                "Website Conversion Improvement",
                "Services are presented without a detected booking or inquiry conversion path, leaving a potential gap between visitor interest and action.",
                [
                    "Services signal detected",
                    "No booking capability detected",
                    "No lead/inquiry form detected",
                ],
                impact=70,
                confidence=0.80,
            )

        # Reputation is useful when there is evidence of reputation to leverage;
        # missing social media by itself is deliberately not a major opportunity.
        if signals.get("reviews") and not signals.get("review_cta"):
            add(
                "reputation_marketing",
                "Reputation & Review Marketing",
                "Reviews or testimonials are present, creating an opportunity to turn existing proof into stronger conversion and follow-up assets.",
                ["Reviews/testimonials detected", "No clear review CTA detected"],
                impact=55,
                confidence=0.72,
            )

        if signals.get("newsletter") and not signals.get("lead_form"):
            add(
                "nurture_automation",
                "Email Nurture Automation",
                "The website offers an audience-capture mechanism that could support automated nurture sequences and re-engagement.",
                ["Newsletter/email subscription signal detected"],
                impact=60,
                confidence=0.76,
            )

        if signals.get("live_chat"):
            add(
                "chat_automation",
                "Website Chat Automation",
                "A live-chat channel is present, creating potential for automated first response, qualification, routing, and after-hours handling.",
                ["Live-chat signal detected"],
                impact=58,
                confidence=0.74,
            )

        if signals.get("ecommerce"):
            add(
                "ecommerce_automation",
                "E-commerce Follow-up Automation",
                "The website has e-commerce signals, creating potential for abandoned-cart, order-status, review-request, and customer re-engagement workflows.",
                ["E-commerce capability detected"],
                impact=78,
                confidence=0.84,
            )

        if signals.get("social") and signals.get("reviews"):
            # No score: this is useful context for outreach, not necessarily a gap.
            pass

        return sorted(
            opportunities,
            key=lambda item: (-int(item["score"]), item["type"]),
        )
