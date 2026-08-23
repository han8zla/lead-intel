import re
from typing import Any

from bs4 import BeautifulSoup


class HTMLProcessor:
    """
    Converts raw HTML into structured lead information.

    This class does NOT:
    - open websites
    - use Playwright
    - make HTTP requests
    - interact with browsers

    It only receives HTML and extracts information from it.
    """

    GHOST_EMAIL_DOMAINS = {
        "zendesk.com",
        "intercom.com",
        "drift.com",
        "hubspot.com",
        "facebook.com",
        "google.com",
        "sentry.io",
        "example.com",
        "email.com",
        "yelp.com",
        "squarespace.com",
        "grammarly.com",
    }

    TOLL_FREE_PREFIXES = {
        "888",
        "800",
        "877",
        "866",
    }

    EMAIL_PATTERN = re.compile(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    )

    PHONE_PATTERN = re.compile(
        r"(\+?1?\s*[-.\)]?\s*\(?\d{3}\)?\s*[-.\s]?\d{3}\s*[-.\s]?\d{4})"
    )

    REMOVE_TAGS = (
        "script",
        "style",
        "noscript",
        "iframe",
        "svg",
    )

    def process(self, html: str) -> dict[str, Any]:
        """
        Parse raw HTML and return structured data.

        Args:
            html: Raw HTML source.

        Returns:
            {
                "text": str,
                "emails": list[str],
                "phones": list[str],
            }

        Raises:
            ValueError: If HTML is empty or invalid.
        """

        if not html or not html.strip():
            raise ValueError("HTML content cannot be empty.")

        soup = self._build_soup(html)

        self._remove_junk(soup)

        text = self._extract_text(soup)
        emails = self._extract_emails(soup, html)
        phones = self._extract_phones(soup, text)

        return {
            "text": text,
            "emails": emails,
            "phones": phones,
        }

    def _build_soup(self, html: str) -> BeautifulSoup:
        """
        Build the BeautifulSoup document.

        lxml is preferred because it is fast and tolerant of
        imperfect HTML.
        """

        try:
            return BeautifulSoup(html, "lxml")
        except Exception:
            # Fallback parser in case lxml isn't available.
            return BeautifulSoup(html, "html.parser")

    def _remove_junk(self, soup: BeautifulSoup) -> None:
        """
        Remove elements that are unlikely to contain useful
        business information.
        """

        for tag in soup.find_all(self.REMOVE_TAGS):
            tag.decompose()

        # Remove inline hidden elements.
        for tag in soup.find_all(
            True,
            attrs={
                "style": lambda value: (
                    value
                    and "display:none" in value.replace(" ", "").lower()
                )
            },
        ):
            tag.decompose()

        # Remove elements explicitly hidden from assistive technology.
        for tag in soup.find_all(
            True,
            attrs={"aria-hidden": "true"},
        ):
            tag.decompose()

    def _extract_text(self, soup: BeautifulSoup) -> str:
        """Extract normalized visible text."""

        text = soup.get_text(
            separator=" ",
            strip=True,
        )

        return re.sub(r"\s+", " ", text).strip()

    def _extract_emails(
        self,
        soup: BeautifulSoup,
        html: str,
    ) -> list[str]:
        """
        Extract emails using two strategies:

        1. mailto links — higher confidence
        2. regex over HTML — catches emails not represented
           as mailto links
        """

        high_confidence = set()

        # First: explicit mailto links.
        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()

            if href.lower().startswith("mailto:"):
                email = (
                    href[7:]
                    .split("?", 1)[0]
                    .strip()
                    .lower()
                )

                if email and self._is_valid_email_candidate(email):
                    high_confidence.add(email)

        # Second: regex extraction.
        regex_emails = set(
            match.lower()
            for match in self.EMAIL_PATTERN.findall(html)
        )

        filtered_regex = {
            email
            for email in regex_emails
            if self._is_valid_email_candidate(email)
        }

        # Preserve high-confidence emails first.
        result = list(high_confidence)

        for email in sorted(filtered_regex):
            if email not in high_confidence:
                result.append(email)

        return result

    def _is_valid_email_candidate(self, email: str) -> bool:
        """Filter obvious third-party/tracking emails."""

        email_lower = email.lower()

        return not any(
            ghost_domain in email_lower
            for ghost_domain in self.GHOST_EMAIL_DOMAINS
        )

    def _extract_phones(
        self,
        soup: BeautifulSoup,
        text: str,
    ) -> list[str]:
        """
        Extract phone numbers.

        tel: links receive priority.
        Regex extraction provides a fallback.
        """

        high_confidence = set()

        # First: explicit tel links.
        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()

            if href.lower().startswith("tel:"):
                phone = href[4:].strip()

                if phone and not self._is_toll_free(phone):
                    high_confidence.add(phone)

        # Second: regex over visible text.
        regex_phones = set(
            match.strip()
            for match in self.PHONE_PATTERN.findall(text)
        )

        filtered_regex = {
            phone
            for phone in regex_phones
            if not self._is_toll_free(phone)
        }

        result = list(high_confidence)

        for phone in sorted(filtered_regex):
            if phone not in high_confidence:
                result.append(phone)

        return result

    def _is_toll_free(self, phone: str) -> bool:
        """
        Determine whether a phone number begins with one of
        our excluded toll-free prefixes.
        """

        normalized = re.sub(
            r"[^0-9]",
            "",
            phone,
        )

        # Handle +1XXXXXXXXXX / 1XXXXXXXXXX.
        if len(normalized) == 11 and normalized.startswith("1"):
            normalized = normalized[1:]

        if len(normalized) < 10:
            return False

        area_code = normalized[:3]

        return area_code in self.TOLL_FREE_PREFIXES