import html as html_lib
import json
import re
from urllib.parse import urlparse
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
    CTA_MARKERS = ("book", "schedule", "contact", "request", "quote", "get started", "call now", "learn more", "buy now", "shop now", "apply", "sign up", "subscribe", "pay")
    TECHNOLOGY_DOMAINS = {
        "calendly.com": "calendly",
        "hubspot.com": "hubspot",
        "hubspotusercontent.com": "hubspot",
        "intercom.io": "intercom",
        "intercomcdn.com": "intercom",
        "drift.com": "drift",
        "zendesk.com": "zendesk",
        "stripe.com": "stripe",
        "squareup.com": "square",
        "acuityscheduling.com": "acuity_scheduling",
        "simplepractice.com": "simplepractice",
        "janeapp.com": "janeapp",
    }

    def process(self, html: str) -> dict[str, Any]:
        if not html or not html.strip():
            raise ValueError("HTML content cannot be empty.")
        original_html = html
        soup = self._build_soup(html)
        emails = self._extract_emails(soup, original_html)
        features = self._extract_features(soup, original_html)
        dom = self._extract_dom_intelligence(soup)
        self._remove_junk(soup)
        text = self._extract_text(soup)
        phones = self._extract_phones(soup, text)
        return {"text": text, "emails": emails, "phones": phones, "features": features, "dom": dom}

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

    def _extract_dom_intelligence(self, soup: BeautifulSoup) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        if title:
            metadata["title"] = title[:300]
        description = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
        if description and description.get("content"):
            metadata["description"] = str(description["content"])[:500]
        canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
        if canonical and canonical.get("href"):
            metadata["canonical"] = str(canonical["href"])[:500]
        language = soup.html.get("lang") if soup.html else None
        if language:
            metadata["language"] = str(language)[:30]

        headings = {
            level: [tag.get_text(" ", strip=True)[:240] for tag in soup.find_all(level) if tag.get_text(" ", strip=True)][:20]
            for level in ("h1", "h2", "h3")
        }

        links = []
        external_domains = set()
        for tag in soup.find_all("a", href=True):
            href = str(tag.get("href", "")).strip()
            text = tag.get_text(" ", strip=True)[:180]
            if not href and not text:
                continue
            link_type = self._classify_link(text, href)
            parsed = urlparse(href)
            if parsed.netloc:
                external_domains.add(parsed.netloc.lower().removeprefix("www."))
            if link_type or text or href.startswith(("http", "/")):
                links.append({"text": text, "href": href[:500], "type": link_type or "other"})

        buttons = []
        for tag in soup.find_all(["button", "input"]):
            text = tag.get_text(" ", strip=True) or str(tag.get("value") or "")
            aria = str(tag.get("aria-label") or "")
            label = (text or aria).strip()
            if label:
                buttons.append({
                    "text": label[:180],
                    "type": self._classify_cta(label),
                    "aria_label": aria[:180],
                })

        forms = []
        for form in soup.find_all("form"):
            fields = []
            for field in form.find_all(["input", "textarea", "select", "button"]):
                fields.append({
                    "tag": field.name,
                    "name": str(field.get("name") or "")[:120],
                    "id": str(field.get("id") or "")[:120],
                    "type": str(field.get("type") or field.name)[:50],
                    "placeholder": str(field.get("placeholder") or "")[:180],
                    "aria_label": str(field.get("aria-label") or "")[:180],
                    "autocomplete": str(field.get("autocomplete") or "")[:80],
                })
            forms.append({
                "action": str(form.get("action") or "")[:500],
                "method": str(form.get("method") or "get").lower(),
                "id": str(form.get("id") or "")[:120],
                "name": str(form.get("name") or "")[:120],
                "aria_label": str(form.get("aria-label") or "")[:180],
                "fields": fields[:40],
            })

        json_ld = []
        for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
            raw = script.string or script.get_text()
            if not raw.strip():
                continue
            try:
                json_ld.append(json.loads(raw))
            except (TypeError, ValueError):
                json_ld.append({"_parse_error": True, "preview": raw[:500]})

        scripts = []
        technologies = set()
        for tag in soup.find_all("script", src=True):
            src = str(tag.get("src", ""))[:500]
            scripts.append(src)
            domain = urlparse(src).netloc.lower().removeprefix("www.")
            for known_domain, technology in self.TECHNOLOGY_DOMAINS.items():
                if domain == known_domain or domain.endswith("." + known_domain):
                    technologies.add(technology)
        for domain in external_domains:
            for known_domain, technology in self.TECHNOLOGY_DOMAINS.items():
                if domain == known_domain or domain.endswith("." + known_domain):
                    technologies.add(technology)

        attribute_samples = []
        for tag in soup.find_all(True):
            attrs = {}
            for key, value in tag.attrs.items():
                if key.startswith("aria-") or key.startswith("data-") or key in {"role", "name", "id", "class"}:
                    attrs[key] = (" ".join(value) if isinstance(value, list) else str(value))[:240]
            if attrs:
                attribute_samples.append({"tag": tag.name, "attributes": attrs})
            if len(attribute_samples) >= 100:
                break

        return {
            "metadata": metadata,
            "headings": headings,
            "links": links[:150],
            "buttons": buttons[:80],
            "forms": forms[:20],
            "json_ld": json_ld[:20],
            "scripts": scripts[:100],
            "external_domains": sorted(external_domains)[:100],
            "technologies": sorted(technologies),
            "attribute_samples": attribute_samples,
        }

    def _classify_link(self, text: str, href: str) -> str:
        value = f"{text} {href}".lower()
        if any(marker in value for marker in ("book appointment", "schedule", "appointment", "book now")):
            return "booking"
        if any(marker in value for marker in ("patient portal", "client portal", "login", "sign in")):
            return "portal"
        if any(marker in value for marker in ("pay bill", "payment", "pay online", "billing")):
            return "payment"
        if any(marker in value for marker in ("contact", "get in touch", "request a quote", "quote")):
            return "contact"
        if any(marker in value for marker in ("review", "testimonial")):
            return "review"
        if any(marker in value for marker in ("apply", "careers", "jobs", "join our team")):
            return "recruitment"
        if any(marker in value for marker in ("referral", "refer a patient")):
            return "referral"
        if any(marker in value for marker in ("shop", "cart", "checkout", "buy")):
            return "commerce"
        return ""

    def _classify_cta(self, text: str) -> str:
        lower = text.lower()
        for marker in self.CTA_MARKERS:
            if marker in lower:
                return marker.replace(" ", "_")
        return "other"

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
