import json
import re
from typing import Any

from bs4 import BeautifulSoup


class BusinessAnalyzer:
    """Baseline deterministic website/business intelligence analyzer."""

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

    def analyze(
        self,
        url: str,
        html: str = "",
        text: str = "",
        scraped_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Analyze either raw HTML or the normalized WebsiteIngestor result."""
        scraped_data = scraped_data or {}

        if not text:
            text = str(scraped_data.get("text") or "")

        pages = [str(page) for page in scraped_data.get("pages", []) if page]

        # Raw HTML is preferred when supplied. In the current ingestion pipeline
        # only normalized text/pages/contact fields may be available, so those
        # fields are also valid evidence.
        soup = BeautifulSoup(html, "lxml") if html else BeautifulSoup("", "lxml")
        normalized_text = re.sub(
            r"\s+", " ", text or soup.get_text(" ", strip=True)
        ).strip()
        lower_html = html.lower()
        lower_text = normalized_text.lower()

        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        description = ""
        description_tag = soup.find(
            "meta", attrs={"name": re.compile("^description$", re.I)}
        )
        if description_tag:
            description = str(description_tag.get("content") or "").strip()

        schema_types = self._schema_types(soup) if html else []
        links = [str(tag.get("href") or "") for tag in soup.find_all("a", href=True)] if html else []

        has_email = self._emails(lower_html or lower_text)
        has_phone = self._phone_signal(soup, lower_text)

        if scraped_data.get("emails"):
            has_email = True
        if scraped_data.get("phones"):
            has_phone = True

        has_contact_page = self._has_any(
            lower_text, self.SIGNALS["contact_page"]
        ) or any("/contact" in page.lower() for page in pages)

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

        opportunity_score, opportunities = self._score(
            signals=signals,
            text_length=len(normalized_text),
        )

        return {
            "url": url,
            "title": title,
            "description": description,
            "schema_types": schema_types,
            "signals": signals,
            "opportunity_score": opportunity_score,
            "opportunities": opportunities,
            "content_length": len(normalized_text),
            "link_count": len(links),
            "pages_analyzed": pages,
        }

    @staticmethod
    def _empty_result(url: str) -> dict[str, Any]:
        return {
            "url": url,
            "title": "",
            "description": "",
            "schema_types": [],
            "signals": {},
            "opportunity_score": 0,
            "opportunities": [],
            "content_length": 0,
            "link_count": 0,
            "pages_analyzed": [],
        }

    @staticmethod
    def _has_any(value: str, patterns: tuple[str, ...]) -> bool:
        return any(pattern in value for pattern in patterns)

    @staticmethod
    def _emails(value: str) -> bool:
        return bool(
            re.search(
                r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                value,
            )
        )

    @staticmethod
    def _phone_signal(soup: BeautifulSoup, text: str) -> bool:
        if soup.find("a", href=re.compile(r"^tel:", re.I)):
            return True
        return bool(
            re.search(
                r"(?<!\d)\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)",
                text,
            )
        )

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
                if isinstance(item, dict):
                    schema_type = item.get("@type")
                    if isinstance(schema_type, list):
                        types.update(str(value) for value in schema_type)
                    elif schema_type:
                        types.add(str(schema_type))

        return sorted(types)

    def _score(
        self,
        signals: dict[str, bool],
        text_length: int,
    ) -> tuple[int, list[str]]:
        score = 0
        opportunities = []

        if not signals.get("email"):
            score += self.OPPORTUNITY_WEIGHTS["missing_email"]
            opportunities.append("No visible email signal detected")

        if not signals.get("phone"):
            score += self.OPPORTUNITY_WEIGHTS["missing_phone"]
            opportunities.append("No visible phone signal detected")

        if not signals.get("contact_page"):
            score += self.OPPORTUNITY_WEIGHTS["missing_contact_page"]
            opportunities.append("No clear contact-page signal detected")

        if not signals.get("booking") and not signals.get("lead_form"):
            score += self.OPPORTUNITY_WEIGHTS["no_booking_or_lead_form"]
            opportunities.append("No clear booking or lead form signal detected")

        if text_length < 500:
            score += self.OPPORTUNITY_WEIGHTS["weak_content"]
            opportunities.append("Website has limited visible text")

        if not signals.get("services"):
            score += self.OPPORTUNITY_WEIGHTS["no_services_signal"]
            opportunities.append("No clear services signal detected")

        if not signals.get("social"):
            score += self.OPPORTUNITY_WEIGHTS["no_social_signal"]
            opportunities.append("No major social-profile signal detected")

        return min(score, 100), opportunities
