import json
import re
from typing import Any

from bs4 import BeautifulSoup

from processors.opportunity_detector import OpportunityDetector


class BusinessAnalyzer:
    """Deterministic business intelligence layer for scraped websites."""

    SIGNAL_PATTERNS = {
        "contact_page": (
            "contact us", "contact page", "get in touch", "contact information",
            "contact details", "reach us", "contact/",
        ),
        "booking": (
            "book online", "book an appointment", "schedule an appointment",
            "schedule a consultation", "schedule your appointment", "appointment request",
            "appointments", "make an appointment", "book now", "reserve now",
        ),
        "lead_form": (
            "contact form", "inquiry form", "enquiry form", "request a quote",
            "request information", "request info", "get a quote", "get started",
            "submit your inquiry", "send us a message", "send message",
            "tell us about your", "request an appointment",
        ),
        "services": (
            "our services", "services", "what we do", "treatments", "specialties",
            "solutions", "service areas",
        ),
        "social": (
            "facebook.com", "instagram.com", "linkedin.com", "youtube.com",
            "tiktok.com", "x.com/", "twitter.com",
        ),
        "ecommerce": (
            "add to cart", "shopping cart", "checkout", "shop now", "buy now",
            "product catalog", "products",
        ),
        "reviews": (
            "reviews", "testimonials", "google reviews", "patient reviews",
            "customer reviews", "what our clients say",
        ),
        "newsletter": (
            "newsletter", "subscribe to our", "subscribe for updates", "email updates",
            "join our mailing list",
        ),
        "live_chat": (
            "live chat", "chat with us", "chat now", "online chat", "start a chat",
        ),
        "review_cta": (
            "leave a review", "write a review", "review us", "review on google",
        ),
    }

    def __init__(self) -> None:
        self.opportunity_detector = OpportunityDetector()

    def analyze(
        self,
        url: str,
        html: str = "",
        text: str = "",
        scraped_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        scraped_data = scraped_data or {}
        if not text:
            text = str(scraped_data.get("text") or "")

        pages = [str(page) for page in scraped_data.get("pages", []) if page]
        soup = BeautifulSoup(html, "lxml") if html else BeautifulSoup("", "lxml")
        normalized_text = re.sub(r"\s+", " ", text or soup.get_text(" ", strip=True)).strip()
        lower_html = html.lower()
        lower_text = normalized_text.lower()
        combined = f"{lower_html} {lower_text}"

        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        description = ""
        description_tag = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
        if description_tag:
            description = str(description_tag.get("content") or "").strip()

        schema_types = self._schema_types(soup) if html else []
        links = [str(tag.get("href") or "") for tag in soup.find_all("a", href=True)] if html else []

        has_email = self._emails(combined) or bool(scraped_data.get("emails"))
        has_phone = self._phone_signal(soup, lower_text) or bool(scraped_data.get("phones"))
        has_contact_page = self._contact_signal(lower_text, pages)

        # When HTML is available, use the DOM. In the worker the ingestor may
        # only return text, so use a conservative text-based form heuristic too.
        form_detected = bool(soup.find("form")) if html else False
        text_form_detected = self._text_form_signal(lower_text)
        has_lead_form = form_detected or text_form_detected or bool(scraped_data.get("lead_forms"))

        signals = {
            "contact_page": has_contact_page,
            "booking": self._booking_signal(combined),
            "lead_form": has_lead_form,
            "phone": has_phone,
            "email": has_email,
            "services": self._has_any(combined, self.SIGNAL_PATTERNS["services"]),
            "social": self._has_any(combined, self.SIGNAL_PATTERNS["social"]),
            "ecommerce": self._has_any(combined, self.SIGNAL_PATTERNS["ecommerce"]),
            "reviews": self._has_any(combined, self.SIGNAL_PATTERNS["reviews"]),
            "newsletter": self._has_any(combined, self.SIGNAL_PATTERNS["newsletter"]),
            "live_chat": self._has_any(combined, self.SIGNAL_PATTERNS["live_chat"]),
            "review_cta": self._has_any(combined, self.SIGNAL_PATTERNS["review_cta"]),
        }

        # Explicit evidence makes every boolean auditable by the UI and useful
        # to the later AI outreach layer.
        signal_evidence = self._signal_evidence(
            signals=signals,
            text=lower_text,
            pages=pages,
            form_detected=form_detected,
            text_form_detected=text_form_detected,
            scraped_data=scraped_data,
        )

        business_name = self._business_name(title, normalized_text, url)
        industry = self._industry(normalized_text, schema_types)
        services = self._services(normalized_text)

        opportunities = self.opportunity_detector.detect(
            signals=signals,
            text=normalized_text,
            pages=pages,
            industry=industry,
        )

        # Overall score measures the strength of actionable opportunities, not
        # the number of missing website features. This prevents "no Instagram"
        # from artificially making a company look like a great sales target.
        opportunity_score = self._overall_score(opportunities)

        return {
            "url": url,
            "business_name": business_name,
            "industry": industry,
            "services": services,
            "title": title,
            "description": description,
            "schema_types": schema_types,
            "signals": signals,
            "signal_evidence": signal_evidence,
            "opportunity_score": opportunity_score,
            "opportunities": opportunities,
            "content_length": len(normalized_text),
            "link_count": len(links),
            "pages_analyzed": pages,
        }

    @staticmethod
    def _business_name(title: str, text: str, url: str) -> str:
        if title:
            cleaned = re.split(r"\s+[|–-]\s+", title)[0].strip()
            if cleaned:
                return cleaned
        match = re.search(r"(?:welcome to|about)\s+([A-Z][A-Za-z0-9 &'.,-]{2,60})", text, re.I)
        if match:
            return match.group(1).strip(" .,")
        host = url.split("//")[-1].split("/")[0].removeprefix("www.")
        return host.split(".")[0].replace("-", " ").replace("_", " ").title()

    @staticmethod
    def _industry(text: str, schema_types: list[str]) -> str:
        value = f"{text} {' '.join(schema_types)}".lower()
        if any(word in value for word in (
            "medical clinic", "medicalclinic", "physician", "doctor", "healthcare",
            "telemedicine", "primary care", "family medicine", "hospital", "dentist",
        )):
            return "healthcare"
        if any(word in value for word in ("real estate", "realtor", "property management", "homes for sale")):
            return "real_estate"
        if any(word in value for word in ("ecommerce", "add to cart", "checkout", "shop now")):
            return "ecommerce"
        if any(word in value for word in ("law firm", "attorney", "legal services")):
            return "legal"
        if any(word in value for word in ("accounting", "bookkeeping", "tax preparation")):
            return "accounting"
        if any(word in value for word in (
            "plumbing", "electrician", "handyman", "roofing", "hvac", "contractor",
        )):
            return "home_services"
        return "unknown"

    @staticmethod
    def _services(text: str) -> list[str]:
        patterns = (
            "primary care", "telemedicine", "family medicine", "urgent care",
            "consulting", "bookkeeping", "accounting", "real estate",
            "property management", "plumbing", "electrical", "roofing", "hvac",
        )
        lower = text.lower()
        return [pattern for pattern in patterns if pattern in lower]

    @classmethod
    def _contact_signal(cls, text: str, pages: list[str]) -> bool:
        return cls._has_any(text, cls.SIGNAL_PATTERNS["contact_page"]) or any(
            "/contact" in page.lower() or "contact-us" in page.lower() for page in pages
        )

    @classmethod
    def _booking_signal(cls, value: str) -> bool:
        # Avoid treating generic "schedule" mentions as a booking system.
        return cls._has_any(value, cls.SIGNAL_PATTERNS["booking"])

    @staticmethod
    def _text_form_signal(text: str) -> bool:
        # Contact forms often render as plain text after parsing, so the word
        # "form" is not required. Require several form-field/action markers to
        # avoid confusing ordinary prose with a form.
        field_markers = (
            "your name", "full name", "first name", "last name", "email address",
            "phone number", "your email", "message", "subject",
        )
        action_markers = ("submit", "send message", "send us a message", "get a quote", "request")
        field_hits = sum(marker in text for marker in field_markers)
        action_hits = sum(marker in text for marker in action_markers)
        return field_hits >= 2 and action_hits >= 1

    @classmethod
    def _signal_evidence(
        cls,
        *,
        signals: dict[str, bool],
        text: str,
        pages: list[str],
        form_detected: bool,
        text_form_detected: bool,
        scraped_data: dict[str, Any],
    ) -> dict[str, list[str]]:
        evidence: dict[str, list[str]] = {}
        page_names = [page.rsplit("/", 2)[-2] if "/" in page.rstrip("/") else page for page in pages]

        for name, present in signals.items():
            if not present:
                evidence[name] = []
                continue
            evidence[name] = [f"{name.replace('_', ' ').title()} signal detected"]

        if signals.get("contact_page"):
            evidence["contact_page"] = ["Contact page/content detected"]
            if any("contact" in name.lower() for name in page_names):
                evidence["contact_page"].append("Contact page included in analyzed pages")
        if signals.get("booking"):
            evidence["booking"] = ["Appointment/booking language detected"]
        if signals.get("lead_form"):
            evidence["lead_form"] = []
            if form_detected:
                evidence["lead_form"].append("HTML form element detected")
            if text_form_detected:
                evidence["lead_form"].append("Multiple form-field/action markers detected in visible text")
            if scraped_data.get("lead_forms"):
                evidence["lead_form"].append("Lead-form metadata supplied by ingestion")
        if signals.get("email"):
            evidence["email"] = [f"{len(scraped_data.get('emails', [])) or 1} email signal(s) detected"]
        if signals.get("phone"):
            evidence["phone"] = [f"{len(scraped_data.get('phones', [])) or 1} phone signal(s) detected"]
        return evidence

    @staticmethod
    def _has_any(value: str, patterns: tuple[str, ...]) -> bool:
        return any(pattern in value for pattern in patterns)

    @staticmethod
    def _emails(value: str) -> bool:
        return bool(re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", value))

    @staticmethod
    def _phone_signal(soup: BeautifulSoup, text: str) -> bool:
        if soup.find("a", href=re.compile(r"^tel:", re.I)):
            return True
        return bool(re.search(r"(?<!\d)\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)", text))

    @staticmethod
    def _schema_types(soup: BeautifulSoup) -> list[str]:
        types = set()
        for script in soup.find_all("script", type="application/ld+json"):
            raw = script.string or script.get_text()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict) and item.get("@type"):
                    value = item["@type"]
                    types.update(str(x) for x in value) if isinstance(value, list) else types.add(str(value))
        return sorted(types)

    @staticmethod
    def _overall_score(opportunities: list[dict[str, Any]]) -> int:
        if not opportunities:
            return 0
        scores = [max(0, min(100, int(item.get("score", 0)))) for item in opportunities]
        # Top opportunity matters most; additional independent opportunities add
        # signal without allowing duplicated rules to push the total to 100.
        weights = (0.55, 0.30, 0.15)
        return round(sum(score * weights[i] for i, score in enumerate(scores[:3])))
