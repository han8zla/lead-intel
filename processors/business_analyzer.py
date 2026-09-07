import json
import re
from typing import Any

from bs4 import BeautifulSoup

from processors.opportunity_detector import OpportunityDetector


class BusinessAnalyzer:
    """Deterministic business intelligence layer for scraped websites."""

    SIGNAL_PATTERNS = {
        "contact_page": ("contact us", "contact page", "get in touch", "contact information", "contact details", "reach us", "contact/"),
        "booking": ("book online", "book an appointment", "schedule an appointment", "schedule a consultation", "schedule your appointment", "appointment request", "appointments", "make an appointment", "book now", "reserve now"),
        "lead_form": ("contact form", "inquiry form", "enquiry form", "request a quote", "request information", "request info", "get a quote", "get started", "submit your inquiry", "send us a message", "send message", "tell us about your", "request an appointment"),
        "services": ("our services", "services", "what we do", "treatments", "specialties", "solutions", "service areas"),
        "social": ("facebook.com", "instagram.com", "linkedin.com", "youtube.com", "tiktok.com", "x.com/", "twitter.com"),
        "ecommerce": ("add to cart", "shopping cart", "checkout", "shop now", "buy now", "product catalog", "products"),
        "reviews": ("reviews", "testimonials", "google reviews", "patient reviews", "customer reviews", "what our clients say"),
        "newsletter": ("newsletter", "subscribe to our", "subscribe for updates", "email updates", "join our mailing list"),
        "live_chat": ("live chat", "chat with us", "chat now", "online chat", "start a chat"),
        "review_cta": ("leave a review", "write a review", "review us", "review on google"),
    }

    def __init__(self) -> None:
        self.opportunity_detector = OpportunityDetector()

    def analyze(self, url: str, html: str = "", text: str = "", scraped_data: dict[str, Any] | None = None) -> dict[str, Any]:
        scraped_data = scraped_data or {}
        if not text:
            text = str(scraped_data.get("text") or "")
        pages = [str(page) for page in scraped_data.get("pages", []) if page]
        page_details = [item for item in scraped_data.get("page_details", []) if isinstance(item, dict)]
        soup = BeautifulSoup(html, "lxml") if html else BeautifulSoup("", "lxml")
        normalized_text = re.sub(r"\s+", " ", text or soup.get_text(" ", strip=True)).strip()
        lower_html, lower_text = html.lower(), normalized_text.lower()
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

        # Page-level DOM features are authoritative when available. This fixes
        # cases where a contact form exists on /contact/ but disappears from the
        # aggregated text representation.
        page_signal = self._aggregate_page_features(page_details)
        form_detected = bool(soup.find("form")) if html else False
        text_form_detected = self._text_form_signal(lower_text)
        has_lead_form = bool(page_signal.get("lead_form")) or form_detected or text_form_detected or bool(scraped_data.get("lead_forms"))

        def feature(name: str, fallback_patterns: tuple[str, ...]) -> bool:
            if name in page_signal:
                return bool(page_signal[name])
            return self._has_any(combined, fallback_patterns)

        signals = {
            "contact_page": has_contact_page,
            "booking": feature("booking", self.SIGNAL_PATTERNS["booking"]),
            "lead_form": has_lead_form,
            "phone": has_phone,
            "email": has_email,
            "services": self._has_any(combined, self.SIGNAL_PATTERNS["services"]),
            "social": feature("social", self.SIGNAL_PATTERNS["social"]),
            "ecommerce": feature("ecommerce", self.SIGNAL_PATTERNS["ecommerce"]),
            "reviews": feature("reviews", self.SIGNAL_PATTERNS["reviews"]),
            "newsletter": feature("newsletter", self.SIGNAL_PATTERNS["newsletter"]),
            "live_chat": feature("live_chat", self.SIGNAL_PATTERNS["live_chat"]),
            "review_cta": feature("review_cta", self.SIGNAL_PATTERNS["review_cta"]),
        }

        signal_evidence = self._signal_evidence(signals, lower_text, pages, form_detected, text_form_detected, scraped_data, page_details)
        business_name = self._business_name(title, normalized_text, url)
        industry = self._industry(normalized_text, schema_types)
        services = self._services(normalized_text)
        opportunities = self.opportunity_detector.detect(signals=signals, text=normalized_text, pages=pages, industry=industry)
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
            "page_details": page_details,
        }

    @staticmethod
    def _aggregate_page_features(page_details: list[dict[str, Any]]) -> dict[str, bool]:
        if not page_details:
            return {}
        names = ("lead_form", "booking", "social", "ecommerce", "reviews", "newsletter", "live_chat", "review_cta")
        return {name: any(bool((page.get("features") or {}).get(name)) for page in page_details) for name in names}

    @staticmethod
    def _page_urls_with_feature(page_details: list[dict[str, Any]], feature: str) -> list[str]:
        return [str(page.get("url")) for page in page_details if (page.get("features") or {}).get(feature)]

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
        if any(word in value for word in ("medical clinic", "medicalclinic", "physician", "doctor", "healthcare", "telemedicine", "primary care", "family medicine", "hospital", "dentist")):
            return "healthcare"
        if any(word in value for word in ("real estate", "realtor", "property management", "homes for sale")):
            return "real_estate"
        if any(word in value for word in ("ecommerce", "add to cart", "checkout", "shop now")):
            return "ecommerce"
        if any(word in value for word in ("law firm", "attorney", "legal services")):
            return "legal"
        if any(word in value for word in ("accounting", "bookkeeping", "tax preparation")):
            return "accounting"
        if any(word in value for word in ("plumbing", "electrician", "handyman", "roofing", "hvac", "contractor")):
            return "home_services"
        return "unknown"

    @staticmethod
    def _services(text: str) -> list[str]:
        patterns = ("primary care", "telemedicine", "family medicine", "urgent care", "consulting", "bookkeeping", "accounting", "real estate", "property management", "plumbing", "electrical", "roofing", "hvac")
        lower = text.lower()
        return [pattern for pattern in patterns if pattern in lower]

    @classmethod
    def _contact_signal(cls, text: str, pages: list[str]) -> bool:
        return cls._has_any(text, cls.SIGNAL_PATTERNS["contact_page"]) or any("/contact" in page.lower() or "contact-us" in page.lower() for page in pages)

    @classmethod
    def _booking_signal(cls, value: str) -> bool:
        return cls._has_any(value, cls.SIGNAL_PATTERNS["booking"])

    @staticmethod
    def _text_form_signal(text: str) -> bool:
        field_markers = ("your name", "full name", "first name", "last name", "email address", "phone number", "your email", "message", "subject")
        action_markers = ("submit", "send message", "send us a message", "get a quote", "request")
        return sum(marker in text for marker in field_markers) >= 2 and sum(marker in text for marker in action_markers) >= 1

    @classmethod
    def _signal_evidence(cls, signals, text, pages, form_detected, text_form_detected, scraped_data, page_details):
        evidence: dict[str, list[str]] = {}
        for name, present in signals.items():
            evidence[name] = [f"{name.replace('_', ' ').title()} signal detected"] if present else []

        feature_page_names = {
            name: cls._page_urls_with_feature(page_details, name)
            for name in ("lead_form", "booking", "social", "ecommerce", "reviews", "newsletter", "live_chat", "review_cta")
        }
        if signals.get("contact_page"):
            evidence["contact_page"] = ["Contact page/content detected"]
            contact_pages = [page for page in pages if "contact" in page.lower()]
            if contact_pages:
                evidence["contact_page"].append(f"Contact page analyzed: {contact_pages[0]}")
        if signals.get("booking"):
            evidence["booking"] = ["Appointment/booking capability detected"]
            evidence["booking"].extend(f"Booking feature found on: {page}" for page in feature_page_names["booking"][:3])
        if signals.get("lead_form"):
            evidence["lead_form"] = []
            evidence["lead_form"].extend(f"Lead/inquiry form found on: {page}" for page in feature_page_names["lead_form"][:3])
            if form_detected:
                evidence["lead_form"].append("HTML form element detected in supplied HTML")
            if text_form_detected:
                evidence["lead_form"].append("Multiple form-field/action markers detected in visible text")
            if scraped_data.get("lead_forms"):
                evidence["lead_form"].append("Lead-form metadata supplied by ingestion")
        if signals.get("email"):
            evidence["email"] = [f"{len(scraped_data.get('emails', [])) or 1} email signal(s) detected"]
        if signals.get("phone"):
            evidence["phone"] = [f"{len(scraped_data.get('phones', [])) or 1} phone signal(s) detected"]
        for name in ("social", "ecommerce", "reviews", "newsletter", "live_chat", "review_cta"):
            if signals.get(name) and feature_page_names[name]:
                evidence[name].extend(f"Detected on: {page}" for page in feature_page_names[name][:3])
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
        weights = (0.55, 0.30, 0.15)
        return round(sum(score * weights[i] for i, score in enumerate(scores[:3])))
