import html as html_lib
import re
from typing import Any

from bs4 import BeautifulSoup


class HTMLProcessor:
    """Converts raw HTML into structured contact and website intelligence."""

    GHOST_EMAIL_DOMAINS = {
        "zendesk.com", "intercom.com", "drift.com", "hubspot.com", "facebook.com",
        "google.com", "sentry.io", "example.com", "email.com", "yelp.com",
        "squarespace.com", "grammarly.com",
    }
    TOLL_FREE_PREFIXES = {"800", "833", "844", "855", "866", "877", "888"}
    EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    OBFUSCATED_EMAIL_PATTERN = re.compile(
        r"([a-zA-Z0-9._%+-]+)\s*(?:\[at\]|\(at\)|\sat\s)\s*"
        r"([a-zA-Z0-9.-]+)\s*(?:\[dot\]|\(dot\)|\sdot\s)([a-zA-Z]{2,})",
        re.IGNORECASE,
    )
    PHONE_PATTERN = re.compile(
        r"(?<!\d)((?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})(?!\d)"
    )
    REMOVE_TAGS = ("script", "style", "noscript", "iframe", "svg")

    FEATURE_PATTERNS = {
        "booking": ("book online", "book an appointment", "schedule an appointment", "schedule a consultation", "schedule your appointment", "appointment request", "appointments", "make an appointment", "book now", "reserve now"),
        "social": ("facebook.com", "instagram.com", "linkedin.com", "youtube.com", "tiktok.com", "x.com/", "twitter.com"),
        "ecommerce": ("add to cart", "shopping cart", "checkout", "shop now", "buy now", "product catalog"),
        "reviews": ("reviews", "testimonials", "google reviews", "patient reviews", "customer reviews", "what our clients say"),
        "newsletter": ("newsletter", "subscribe to our", "subscribe for updates", "email updates", "join our mailing list"),
        "live_chat": ("live chat", "chat with us", "chat now", "online chat", "start a chat"),
        "review_cta": ("leave a review", "write a review", "review us", "review on google"),
    }
    FORM_FIELD_MARKERS = ("name", "full name", "first name", "last name", "email", "phone", "message", "subject", "company")
    FORM_ACTION_MARKERS = ("submit", "send message", "send us a message", "get a quote", "request", "contact us", "get started")

    def process(self, html: str) -> dict[str, Any]:
        if not html or not html.strip():
            raise ValueError("HTML content cannot be empty.")
        original_html = html
        soup = self._build_soup(html)
        emails = self._extract_emails(soup, original_html)
        features = self._extract_features(soup, original_html)
        self._remove_junk(soup)
        text = self._extract_text(soup)
        phones = self._extract_phones(soup, text)
        return {"text": text, "emails": emails, "phones": phones, "features": features}

    def _build_soup(self, html: str) -> BeautifulSoup:
        try:
            return BeautifulSoup(html, "lxml")
        except Exception:
            return BeautifulSoup(html, "html.parser")

    def _remove_junk(self, soup: BeautifulSoup) -> None:
        for tag in soup.find_all(self.REMOVE_TAGS):
            tag.decompose()
        for tag in soup.find_all(True, attrs={"style": lambda value: value and "display:none" in value.replace(" ", "").lower()}):
            tag.decompose()
        for tag in soup.find_all(True, attrs={"aria-hidden": "true"}):
            tag.decompose()

    @staticmethod
    def _extract_text(soup: BeautifulSoup) -> str:
        return re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True)).strip()

    def _extract_features(self, soup: BeautifulSoup, html: str) -> dict[str, Any]:
        raw_text = soup.get_text(" ", strip=True).lower()
        combined = f"{html.lower()} {raw_text}"
        forms = soup.find_all("form")
        form_details = []
        for form in forms:
            fields = []
            for field in form.find_all(["input", "textarea", "select"]):
                label = " ".join(str(field.get(key) or "") for key in ("name", "id", "placeholder", "aria-label")).strip()
                if label:
                    fields.append(label[:120])
            form_details.append({"action": str(form.get("action") or ""), "fields": fields, "text": form.get_text(" ", strip=True)[:300]})

        field_hits = sum(marker in raw_text for marker in self.FORM_FIELD_MARKERS)
        action_hits = sum(marker in raw_text for marker in self.FORM_ACTION_MARKERS)
        lead_form = bool(forms) and any(
            len(detail["fields"]) >= 2 or any(marker in detail["text"].lower() for marker in self.FORM_ACTION_MARKERS)
            for detail in form_details
        )
        lead_form = lead_form or (field_hits >= 2 and action_hits >= 1)

        return {
            "form_count": len(forms),
            "lead_form": lead_form,
            "form_details": form_details[:5],
            "booking": self._has_any(combined, self.FEATURE_PATTERNS["booking"]),
            "social": self._has_any(combined, self.FEATURE_PATTERNS["social"]),
            "ecommerce": self._has_any(combined, self.FEATURE_PATTERNS["ecommerce"]),
            "reviews": self._has_any(combined, self.FEATURE_PATTERNS["reviews"]),
            "newsletter": self._has_any(combined, self.FEATURE_PATTERNS["newsletter"]),
            "live_chat": self._has_any(combined, self.FEATURE_PATTERNS["live_chat"]),
            "review_cta": self._has_any(combined, self.FEATURE_PATTERNS["review_cta"]),
            "cta_count": sum(1 for tag in soup.find_all(["a", "button"]) if self._is_cta(tag.get_text(" ", strip=True))),
        }

    @staticmethod
    def _is_cta(value: str) -> bool:
        lower = value.lower()
        return any(marker in lower for marker in ("book", "schedule", "contact", "request", "quote", "get started", "call now", "learn more", "buy now", "shop now"))

    @staticmethod
    def _has_any(value: str, patterns: tuple[str, ...]) -> bool:
        return any(pattern in value for pattern in patterns)

    def _extract_emails(self, soup: BeautifulSoup, html: str) -> list[str]:
        high_confidence = set()
        candidates = set()
        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            if href.lower().startswith("mailto:"):
                email = href[7:].split("?", 1)[0].strip().lower()
                if self._is_valid_email_candidate(email):
                    high_confidence.add(email)
        for match in self.EMAIL_PATTERN.findall(html):
            candidates.add(html_lib.unescape(match).lower())
        for tag in soup.find_all(True):
            for value in tag.attrs.values():
                values = value if isinstance(value, list) else [value]
                for item in values:
                    if isinstance(item, str):
                        candidates.update(html_lib.unescape(match).lower() for match in self.EMAIL_PATTERN.findall(item))
        for match in self.OBFUSCATED_EMAIL_PATTERN.findall(html_lib.unescape(html)):
            candidates.add(f"{match[0]}@{match[1]}.{match[2]}".lower())
        filtered = {email for email in candidates if self._is_valid_email_candidate(email)}
        return sorted(high_confidence) + sorted(filtered - high_confidence)

    def _is_valid_email_candidate(self, email: str) -> bool:
        if not email or "@" not in email or email.count("@") != 1:
            return False
        local, domain = email.strip().lower().split("@", 1)
        if not local or "." not in domain:
            return False
        return not any(domain == ghost or domain.endswith("." + ghost) for ghost in self.GHOST_EMAIL_DOMAINS)

    def _extract_phones(self, soup: BeautifulSoup, text: str) -> list[str]:
        high_confidence = set()
        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            if href.lower().startswith("tel:"):
                phone = href[4:].strip()
                if phone and not self._is_toll_free(phone):
                    high_confidence.add(phone)
        filtered = {phone.strip() for phone in self.PHONE_PATTERN.findall(text) if not self._is_toll_free(phone)}
        return sorted(high_confidence) + sorted(filtered - high_confidence)

    def _is_toll_free(self, phone: str) -> bool:
        normalized = re.sub(r"[^0-9]", "", phone)
        if len(normalized) == 11 and normalized.startswith("1"):
            normalized = normalized[1:]
        if len(normalized) < 10:
            return False
        return normalized[:3] in self.TOLL_FREE_PREFIXES
