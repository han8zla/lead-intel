from typing import Any


class OpportunityDetector:
    """Evidence-first business opportunity analysis for scraped websites.

    Phase 4 deliberately does not treat a website feature as proof that a
    workflow is missing. It reconstructs visible business journeys, records
    what is observed versus unknown, and only then creates opportunity
    candidates. The priority score is a routing aid, not a probability of sale.
    """

    ANALYSIS_VERSION = "phase4-v2"

    AUDIENCE_PATTERNS = {
        "patients": ("patient", "patients", "new patient", "new patients"),
        "clients": ("client", "clients", "customer", "customers"),
        "families": ("family", "families", "caregiver", "caregivers"),
        "referrers": ("referral", "referrals", "referring", "physician referral"),
        "professionals": ("professionals", "providers", "provider", "supervision", "consultation"),
        "employees": ("careers", "career", "jobs", "hiring", "join our team", "employment"),
        "members": ("membership", "member", "members", "monthly membership"),
    }

    WORKFLOW_PATTERNS = {
        "intake": ("intake", "patient forms", "new patient forms", "application", "registration", "enrollment"),
        "consultation": ("free consultation", "free consult", "consultation", "discovery call", "initial consultation"),
        "referral": ("referral", "referrals", "refer a patient", "referring provider"),
        "follow_up": ("follow-up", "follow up", "followup", "ongoing care", "after your visit", "after your appointment"),
        "recall": ("recall", "re-care", "reactivation", "return visit", "come back", "regular visits"),
        "financing": ("financing", "payment plan", "insurance", "insurance accepted", "pay your bill"),
        "care_coordination": ("care coordination", "care coordinator", "coordinate care", "case management"),
        "recruitment": ("apply", "careers", "jobs", "join our team", "employment", "hiring"),
        "membership": ("membership", "member benefits", "monthly fee", "membership plans"),
        "multi_service": ("services", "programs", "treatments", "specialties", "service areas"),
    }

    def analyze_business(
        self,
        *,
        signals: dict[str, bool],
        text: str = "",
        pages: list[str] | None = None,
        industry: str = "unknown",
        services: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build the business/workflow layer that sits above raw signals."""
        normalized = " ".join((text or "").lower().split())
        pages = pages or []
        services = services or []

        audiences = self._detect_terms(normalized, self.AUDIENCE_PATTERNS)
        workflows = self._detect_terms(normalized, self.WORKFLOW_PATTERNS)
        capabilities = [name for name, present in signals.items() if present]

        conversion_paths = []
        if signals.get("booking"):
            conversion_paths.append("appointment_or_consultation")
        if signals.get("lead_form"):
            conversion_paths.append("inquiry_form")
        if signals.get("phone"):
            conversion_paths.append("phone")
        if signals.get("email"):
            conversion_paths.append("email")
        if signals.get("live_chat"):
            conversion_paths.append("live_chat")
        if signals.get("ecommerce"):
            conversion_paths.append("transaction")

        observed = {
            "website_capabilities": capabilities,
            "conversion_paths": conversion_paths,
            "audiences": audiences,
            "workflows": workflows,
            "services": services,
        }

        unknowns = self._unknown_workflows(signals, workflows, audiences)
        journey = self._journey_steps(signals, workflows, audiences)

        return {
            "analysis_version": self.ANALYSIS_VERSION,
            "business_profile": {
                "industry": industry,
                "audiences": audiences,
                "services": services,
            },
            "customer_journey": journey,
            "observed": observed,
            "unknowns": unknowns,
            "data_quality": self._data_quality(signals, text, pages),
        }

    def detect(
        self,
        *,
        signals: dict[str, bool],
        text: str = "",
        pages: list[str] | None = None,
        industry: str = "unknown",
        services: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return evidence-backed opportunity candidates, not generic feature gaps."""
        pages = pages or []
        services = services or []
        normalized = " ".join((text or "").lower().split())
        business = self.analyze_business(
            signals=signals,
            text=normalized,
            pages=pages,
            industry=industry,
            services=services,
        )
        audiences = business["business_profile"]["audiences"]
        workflows = business["observed"]["workflows"]
        opportunities: list[dict[str, Any]] = []

        def add(
            type_: str,
            title: str,
            impact: int,
            evidence: list[str],
            recommendation: str,
            *,
            confidence: int,
            solution_fit: int,
            unknowns: list[str] | None = None,
        ) -> None:
            if not evidence:
                return
            priority_score = self._priority_score(impact, confidence, solution_fit)
            opportunities.append({
                "type": type_,
                "title": title,
                "priority": self.priority_band(priority_score),
                "score": priority_score,
                "impact": impact,
                "confidence": confidence,
                "solution_fit": solution_fit,
                "evidence": evidence,
                "unknowns": unknowns or [],
                "recommendation": recommendation,
            })

        booking = signals.get("booking", False)
        form = signals.get("lead_form", False)
        contact = signals.get("contact_page", False)
        services_present = signals.get("services", False)
        email = signals.get("email", False)
        phone = signals.get("phone", False)
        reviews = signals.get("reviews", False)
        review_cta = signals.get("review_cta", False)
        newsletter = signals.get("newsletter", False)
        ecommerce = signals.get("ecommerce", False)

        contact_page = self._page_hint(pages, "contact")
        booking_page = self._page_hint(pages, "book", "appointment", "schedule")

        # A booking system proves that booking exists. It does not prove that
        # reminders, no-show recovery, rescheduling or post-visit workflows do
        # not exist. Those are deliberately listed as unknowns.
        if booking:
            evidence = ["Online appointment/consultation capability is visible"]
            if booking_page:
                evidence.append(f"Booking-related page analyzed: {booking_page}")
            if industry == "healthcare":
                evidence.append("Healthcare service model makes the appointment lifecycle commercially relevant")
            if phone or email:
                evidence.append("Direct communication channels are available")
            add(
                "appointment_lifecycle",
                "Appointment Lifecycle Automation",
                90 if industry == "healthcare" else 82,
                evidence,
                "Audit and, where needed, automate confirmation, reminders, rescheduling, no-show recovery and post-appointment follow-up.",
                confidence=82 if booking_page else 76,
                solution_fit=92,
                unknowns=[
                    "Existing reminder/confirmation automation is not visible from the website",
                    "Existing scheduling or practice-management integrations are unknown",
                ],
            )

        # Forms are treated as an intake/conversion event. We do not infer that
        # response handling is manual; we identify the workflow worth auditing.
        if form:
            evidence = ["Website captures an inquiry or lead through a form"]
            if contact_page:
                evidence.append(f"Contact/inquiry content analyzed: {contact_page}")
            if email or phone:
                evidence.append("Direct contact channel is available for routing/follow-up")
            add(
                "inquiry_conversion",
                "Inquiry-to-Response Workflow",
                87,
                evidence,
                "Audit response routing, acknowledgement, qualification and timed follow-up for new inquiries.",
                confidence=84 if contact_page else 77,
                solution_fit=94,
                unknowns=["Current CRM/inbox routing and response SLA are not visible"],
            )

        # Consultation is particularly useful for professional services and
        # care businesses because it identifies a conversion stage, not merely a
        # website feature.
        if "consultation" in workflows and not form and not booking:
            evidence = ["Consultation/discovery step is described in the website content"]
            add(
                "consultation_conversion",
                "Consultation Conversion Workflow",
                84,
                evidence,
                "Create a structured consultation request, qualification, reminder and follow-up workflow.",
                confidence=78,
                solution_fit=93,
                unknowns=["The actual consultation intake and follow-up process is not visible"],
            )

        # Intake/application evidence creates a separate workflow from ordinary
        # marketing inquiries.
        if "intake" in workflows or "referral" in workflows:
            evidence = []
            if "intake" in workflows:
                evidence.append("Intake/application/registration workflow is described")
            if "referral" in workflows:
                evidence.append("Referral workflow is described")
            add(
                "intake_coordination",
                "Intake & Referral Coordination",
                91 if industry == "healthcare" else 84,
                evidence,
                "Map intake/referral stages and automate document collection, routing, status updates and follow-up where appropriate.",
                confidence=83,
                solution_fit=96,
                unknowns=["Internal intake ownership, systems and manual handoffs are not visible"],
            )

        # Multiple audiences are a real workflow signal. This catches cases
        # such as families vs caregivers vs professionals without inventing a
        # generic "lead follow-up" opportunity for everyone.
        if len(audiences) >= 2:
            evidence = [f"Multiple audience groups detected: {', '.join(audiences)}"]
            if "referrers" in audiences:
                evidence.append("Referral/referrer audience is explicitly represented")
            add(
                "audience_routing",
                "Multi-Audience Lead Routing",
                88,
                evidence,
                "Separate incoming requests by audience, route them to the correct workflow and use audience-specific follow-up.",
                confidence=85,
                solution_fit=95,
                unknowns=["Current routing rules and ownership by audience are not visible"],
            )

        if "recruitment" in workflows or "employees" in audiences:
            evidence = ["Recruitment/career workflow is visible"]
            add(
                "recruitment_workflow",
                "Recruitment & Applicant Workflow",
                78,
                evidence,
                "Automate applicant intake, screening, status updates, interview scheduling and follow-up where appropriate.",
                confidence=80,
                solution_fit=88,
                unknowns=["Existing applicant tracking or HR system is not visible"],
            )

        if "membership" in workflows or "members" in audiences:
            evidence = ["Membership model or member audience is visible"]
            add(
                "membership_conversion",
                "Membership Conversion & Onboarding",
                89,
                evidence,
                "Automate membership inquiry, qualification, onboarding, reminders and retention touchpoints around the existing member journey.",
                confidence=84,
                solution_fit=94,
                unknowns=["Existing membership, billing and onboarding systems are not visible"],
            )

        # Follow-up/recall is only proposed when the business content actually
        # describes an ongoing relationship. It is not generated merely because
        # a business has a contact form.
        if "follow_up" in workflows or "recall" in workflows:
            evidence = []
            if "follow_up" in workflows:
                evidence.append("Ongoing follow-up is described in the content")
            if "recall" in workflows:
                evidence.append("Recall/reactivation/return-visit language is present")
            add(
                "retention_reactivation",
                "Follow-up & Reactivation Workflow",
                86,
                evidence,
                "Identify customers/patients who need follow-up, recall or reactivation and automate appropriate reminders and outreach.",
                confidence=79,
                solution_fit=92,
                unknowns=["Existing recall/reactivation process and customer database are not visible"],
            )

        if reviews and not review_cta and (booking or form or services_present):
            evidence = ["Reviews/testimonials are visible", "No explicit review-request workflow is visible"]
            add(
                "reputation_follow_up",
                "Review Request Workflow",
                65,
                evidence,
                "Audit the post-service feedback process and automate review requests where appropriate.",
                confidence=68,
                solution_fit=86,
                unknowns=["Existing review-request system is not visible"],
            )

        # Ecommerce is deliberately conservative: the signal must come from an
        # explicit transaction capability already detected by BusinessAnalyzer.
        if ecommerce:
            evidence = ["Explicit transaction/ecommerce capability detected"]
            add(
                "commerce_lifecycle",
                "Customer & Order Lifecycle",
                80,
                evidence,
                "Audit order confirmation, abandoned-cart, customer support and post-purchase workflows before proposing automation.",
                confidence=82,
                solution_fit=82,
                unknowns=["Actual catalog, cart and fulfillment systems are not visible"],
            )

        # A missing digital conversion path is useful, but it is a lower-level
        # website finding rather than a reason to claim a backend automation gap.
        if contact and not form and not booking and not ecommerce and (services_present or phone or email):
            evidence = ["Contact information is visible", "No dedicated inquiry or booking path was detected"]
            add(
                "conversion_path",
                "Conversion Path Improvement",
                72,
                evidence,
                "Create a measurable inquiry/conversion path before adding downstream automation.",
                confidence=88,
                solution_fit=84,
                unknowns=["Some conversion path may exist outside the analyzed pages"],
            )

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
    def _detect_terms(text: str, patterns: dict[str, tuple[str, ...]]) -> list[str]:
        return [name for name, terms in patterns.items() if any(term in text for term in terms)]

    @staticmethod
    def _unknown_workflows(
        signals: dict[str, bool],
        workflows: list[str],
        audiences: list[str],
    ) -> list[str]:
        unknowns: list[str] = []
        if signals.get("booking"):
            unknowns.extend(["confirmation", "reminders", "rescheduling", "no_show_recovery"])
        if signals.get("lead_form") or "consultation" in workflows:
            unknowns.extend(["response_routing", "qualification", "follow_up"])
        if "intake" in workflows or "referral" in workflows:
            unknowns.extend(["document_collection", "handoffs", "status_updates"])
        if "recruitment" in workflows or "employees" in audiences:
            unknowns.extend(["applicant_screening", "interview_scheduling", "candidate_follow_up"])
        if "membership" in workflows or "members" in audiences:
            unknowns.extend(["onboarding", "retention", "billing_workflow"])
        return list(dict.fromkeys(unknowns))

    @staticmethod
    def _journey_steps(
        signals: dict[str, bool],
        workflows: list[str],
        audiences: list[str],
    ) -> list[str]:
        steps = ["discover"]
        if signals.get("phone") or signals.get("email") or signals.get("lead_form"):
            steps.append("inquire")
        if "referral" in workflows:
            steps.append("referral")
        if "consultation" in workflows:
            steps.append("consultation")
        if signals.get("booking"):
            steps.append("book")
        if "intake" in workflows:
            steps.append("intake")
        if "membership" in workflows:
            steps.append("membership")
        if "follow_up" in workflows or "recall" in workflows:
            steps.append("ongoing_follow_up")
        if signals.get("reviews"):
            steps.append("review")
        if len(audiences) >= 2:
            steps.insert(1, "audience_route")
        return list(dict.fromkeys(steps))

    @staticmethod
    def _data_quality(signals: dict[str, bool], text: str, pages: list[str]) -> dict[str, Any]:
        available = sum(bool(value) for value in signals.values())
        score = min(100, 25 + (available * 5) + (20 if text else 0) + min(20, len(pages) * 4))
        return {
            "score": score,
            "text_present": bool(text.strip()),
            "pages_analyzed": len(pages),
            "signal_count": available,
        }

    @staticmethod
    def _priority_score(impact: int, confidence: int, solution_fit: int) -> int:
        """Priority combines impact, evidence confidence and Handyman fit.

        This is intentionally a routing score, not a probability of purchase.
        Keeping the three inputs visible makes the result auditable and easier
        to calibrate against real Handyman outcomes later.
        """
        values = [max(0, min(100, int(value))) for value in (impact, confidence, solution_fit)]
        return round((values[0] * 0.45) + (values[1] * 0.30) + (values[2] * 0.25))

    @staticmethod
    def priority_band(score: int) -> str:
        if score >= 80:
            return "high"
        if score >= 60:
            return "medium"
        return "low"

    @staticmethod
    def overall_score(opportunities: list[dict[str, Any]]) -> dict[str, Any]:
        """Summarize the best candidates without pretending the number is a sale probability."""
        if not opportunities:
            return {
                "score": 0,
                "band": "weak",
                "breakdown": {
                    "reason": "No evidence-backed automation opportunity identified",
                    "top_opportunity": None,
                },
            }

        top = opportunities[0]
        second = opportunities[1] if len(opportunities) > 1 else None
        # The top candidate drives routing, while the second candidate is a
        # modest supporting signal. This is intentionally simpler than the old
        # top-three weighted score because the candidates are not independent.
        score = round((int(top["score"]) * 0.75) + (int(second["score"]) * 0.25 if second else 0))
        return {
            "score": score,
            "band": OpportunityDetector.priority_band(score),
            "breakdown": {
                "top_opportunity": top["score"],
                "secondary_opportunity": second["score"] if second else None,
                "top_type": top["type"],
                "reason": "Priority reflects the strongest evidence-backed opportunity; it is not a probability of purchase.",
            },
        }

    @staticmethod
    def _page_hint(pages: list[str], *keywords: str) -> str:
        for page in pages:
            lower = page.lower()
            if any(keyword in lower for keyword in keywords):
                return page
        return ""
