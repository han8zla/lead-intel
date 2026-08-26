import json
import re
from typing import Any

from bs4 import BeautifulSoup

from processors.opportunity_detector import OpportunityDetector


class BusinessAnalyzer:
    """Deterministic business intelligence layer for scraped websites."""

    SIGNALS = {
        "contact_page": ("/contact", "contact us", "get in touch"),
        "booking": ("book online", "book an appointment", "schedule", "appointment"),
        "lead_form": ("contact form", "request a quote", "request information", "get started"),
        "phone": ("tel:", "call us", "phone:"),
        "email": ("mailto:", "@"),
        "services": ("services", "our services", "what we do"),
        "social": ("facebook.com", "instagram.com", "linkedin.com", "youtube.com"),
        "ecommerce": ("add to cart", "cart", "checkout", "shop now", "buy now"),
        "reviews": ("reviews", "testimonials", "google reviews"),
    }

    OPPORTUNITY_WEIGHTS = {
        "missing_email": 20,
        "missing_phone": 10,
        "missing_contact_page": 10,
        "no_booking_or_lead_form": 15,
        "weak_content": 10,
        "no_services_signal": 5,
        "no_social_signal": 5,
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

        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        description = ""
        description_tag = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
        if description_tag:
            description = str(description_tag.get("content") or "").strip()

        schema_types = self._schema_types(soup) if html else []
        links = [str(tag.get("href") or "") for tag in soup.find_all("a", href=True)] if html else []

        has_email = self._emails(lower_html or lower_text) or bool(scraped_data.get("emails"))
        has_phone = self._phone_signal(soup, lower_text) or bool(scraped_data.get("phones"))
        has_contact_page = self._has_any(lower_text, self.SIGNALS["contact_page"]) or any(
            "/contact" in page.lower() for page in pages
        )

        signals = {
            "contact_page": has_contact_page,
            "booking": self._has_any(lower_text, self.SIGNALS["booking"]),
            "lead_form": bool(soup.find("form")) or self._has_any(lower_text, self.SIGNALS["lead_form"]),
            "phone": has_phone,
            "email": has_email,
            "services": self._has_any(lower_text, self.SIGNALS["services"]),
            "social": self._has_any(lower_html or lower_text, self.SIGNALS["social"]),
            "ecommerce": self._has_any(lower_text, self.SIGNALS["ecommerce"]),
            "reviews": self._has_any(lower_text, self.SIGNALS["reviews"]),
        }

        business_name = self._business_name(title, normalized_text, url)
        industry = self._industry(normalized_text, schema_types)
        services = self._services(normalized_text)

        opportunity_score, baseline = self._score(signals, len(normalized_text))
        opportunities = self.opportunity_detector.detect(
            signals=signals,
            text=normalized_text,
            pages=pages,
            industry=industry,
        )

        # The detector is the primary actionable score. Keep the baseline as
        # diagnostic context rather than mixing two unrelated scoring systems.
        actionable_score = min(100, sum(int(item["score"]) for item in opportunities))

        return {
            "url": url,
            "business_name": business_name,
            "industry": industry,
            "services": services,
            "title": title,
            "description": description,
            "schema_types": schema_types,
            "signals": signals,
            "opportunity_score": actionable_score,
            "baseline_score": baseline,
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
        if any(word in value for word in ("medicalclinic", "medical", "physician", "doctor", "healthcare", "telemedicine", "primary care")):
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
        patterns = (
            "primary care", "telemedicine", "family medicine", "urgent care",
            "consulting", "bookkeeping", "accounting", "real estate",
            "property management", "plumbing", "electrical", "roofing", "hvac",
        )
        return [pattern for pattern in patterns if pattern in text.lower()]

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

    def _score(self, signals: dict[str, bool], text_length: int) -> tuple[int, list[str]]:
        score = 0
        opportunities = []
        if not signals.get("email"):
            score += 20; opportunities.append("No visible email signal detected")
        if not signals.get("phone"):
            score += 10; opportunities.append("No visible phone signal detected")
        if not signals.get("contact_page"):
            score += 10; opportunities.append("No clear contact-page signal detected")
        if not signals.get("booking") and not signals.get("lead_form"):
            score += 15; opportunities.append("No clear booking or lead form signal detected")
        if text_length < 500:
            score += 10; opportunities.append("Website has limited visible text")
        if not signals.get("services"):
            score += 5; opportunities.append("No clear services signal detected")
        if not signals.get("social"):
            score += 5; opportunities.append("No major social-profile signal detected")
        return min(score, 100), opportunities
