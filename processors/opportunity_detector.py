from typing import Any


class OpportunityDetector:
    """Rule-based detector for commercially meaningful automation opportunities."""

    def detect(
        self,
        *,
        signals: dict[str, bool],
        text: str = "",
        pages: list[str] | None = None,
        industry: str = "unknown",
    ) -> list[dict[str, Any]]:
        pages = pages or []
        text_lower = text.lower()
        opportunities: list[dict[str, Any]] = []

        def add(
            type_: str,
            title: str,
            priority: str,
            impact: int,
            confidence: int,
            evidence: list[str],
            recommendation: str,
        ) -> None:
            if not evidence:
                return
            score = round(impact * (confidence / 100))
            opportunities.append({
                "type": type_,
                "title": title,
                "priority": priority,
                "score": score,
                "impact": impact,
                "confidence": confidence,
                "evidence": evidence,
                "recommendation": recommendation,
            })

        booking = signals.get("booking", False)
        form = signals.get("lead_form", False)
        contact = signals.get("contact_page", False)
        services = signals.get("services", False)
        email = signals.get("email", False)
        phone = signals.get("phone", False)
        reviews = signals.get("reviews", False)
        review_cta = signals.get("review_cta", False)
        newsletter = signals.get("newsletter", False)
        live_chat = signals.get("live_chat", False)
        ecommerce = signals.get("ecommerce", False)

        contact_page = self._page_hint(pages, "contact")
        booking_hint = self._page_hint(pages, "book", "appointment", "schedule")

        # A booking workflow is distinct from inquiry capture. If a booking
        # capability exists, recommend downstream automation rather than a
        # redundant "add a form" opportunity.
        if booking:
            evidence = ["Appointment/booking capability detected"]
            if booking_hint:
                evidence.append(f"Booking-related page analyzed: {booking_hint}")
            if email or phone:
                evidence.append("Direct contact channel available for confirmations/follow-up")
            if industry == "healthcare":
                evidence.append("Healthcare business: appointment reminders and no-show recovery are high-impact workflows")
            add(
                "appointment_follow_up",
                "Appointment Follow-up Automation",
                "high" if industry == "healthcare" else "medium",
                95 if industry == "healthcare" else 82,
                92 if booking_hint else 82,
                evidence,
                "Automate confirmations, reminders, rescheduling prompts, no-show recovery and post-appointment follow-up.",
            )

        # Existing inquiry capture means the opportunity is what happens AFTER
        # submission, not installing another lead form.
        if form:
            evidence = ["Website inquiry/contact form detected"]
            if contact_page:
                evidence.append(f"Form/contact workflow appears on {contact_page}")
            if email or phone:
                evidence.append("Direct contact channel available for routing and follow-up")
            add(
                "inquiry_follow_up",
                "Inquiry Follow-up Automation",
                "high" if email or phone else "medium",
                86,
                90 if contact_page else 78,
                evidence,
                "Route new inquiries automatically, send an immediate acknowledgement, qualify the request and trigger timed follow-ups.",
            )

        # Only recommend lead capture when there is no detectable existing form
        # or booking path. This fixes the previous false-positive overlap.
        if contact and not form and not booking and (services or email or phone):
            evidence = ["Contact page/content detected", "No dedicated inquiry form or booking path detected"]
            if services:
                evidence.append("Services are presented without a clear digital conversion path")
            add(
                "lead_capture",
                "Lead Capture / Inquiry Workflow",
                "high" if services else "medium",
                88 if services else 72,
                84,
                evidence,
                "Add a structured inquiry path and route submissions into a measurable lead workflow.",
            )

        # Conversion optimization is only suggested when the website clearly
        # sells/provides services but has a weak digital conversion path.
        if services and not form and not booking and not live_chat:
            evidence = ["Services/treatments/solutions detected", "No booking, inquiry form or live-chat conversion path detected"]
            add(
                "website_conversion",
                "Website Conversion Optimization",
                "medium",
                76,
                82,
                evidence,
                "Create a clearer primary call-to-action and low-friction conversion path for high-intent visitors.",
            )

        if form and not newsletter:
            evidence = ["Website already captures visitor information through an inquiry form", "No newsletter/subscriber workflow detected"]
            add(
                "lead_nurture",
                "Lead Nurture Automation",
                "medium",
                74,
                72,
                evidence,
                "Turn captured inquiries into a structured nurture sequence while keeping sales follow-up timely and relevant.",
            )

        if reviews and not review_cta:
            evidence = ["Reviews/testimonials detected", "No explicit review-request CTA detected"]
            add(
                "reputation_marketing",
                "Reputation & Review Automation",
                "medium",
                68,
                76,
                evidence,
                "Automate post-service review requests and route positive/negative feedback appropriately.",
            )

        if ecommerce:
            evidence = ["Ecommerce/transaction capability detected"]
            add(
                "ecommerce_automation",
                "Customer & Order Automation",
                "medium",
                80,
                86,
                evidence,
                "Automate order notifications, abandoned-cart recovery, customer follow-up and post-purchase workflows.",
            )

        if newsletter and not form:
            evidence = ["Newsletter/subscriber capture detected", "No inquiry form detected"]
            add(
                "newsletter_nurture",
                "Subscriber Nurture Automation",
                "medium",
                64,
                74,
                evidence,
                "Automate welcome, segmentation and nurture sequences for subscribers.",
            )

        # Social absence is deliberately not an opportunity by itself. A
        # reputation/social recommendation needs another business signal.
        if signals.get("social") and reviews and not review_cta:
            evidence = ["Social presence detected", "Reviews/testimonials detected", "No explicit review-request CTA detected"]
            add(
                "social_reputation",
                "Social & Reputation Workflow",
                "low",
                58,
                65,
                evidence,
                "Connect social proof and review requests into a consistent reputation workflow.",
            )

        # De-duplicate by opportunity type and return strongest first.
        unique: dict[str, dict[str, Any]] = {}
        for item in opportunities:
            current = unique.get(item["type"])
            if current is None or item["score"] > current["score"]:
                unique[item["type"]] = item

        priority_order = {"high": 0, "medium": 1, "low": 2}
        return sorted(
            unique.values(),
            key=lambda item: (-item["score"], priority_order.get(item["priority"], 9)),
        )

    @staticmethod
    def _page_hint(pages: list[str], *keywords: str) -> str:
        for page in pages:
            lower = page.lower()
            if any(keyword in lower for keyword in keywords):
                return page
        return ""
