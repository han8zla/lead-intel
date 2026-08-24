import html as html_lib
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
        "800",
        "833",
        "844",
        "855",
        "866",
        "877",
        "888",
    }

    EMAIL_PATTERN = re.compile(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    )

    OBFUSCATED_EMAIL_PATTERN = re.compile(
        r"([a-zA-Z0-9._%+-]+)\s*(?:\[at\]|\(at\)|\sat\s)"
        r"\s*([a-zA-Z0-9.-]+)\s*(?:\[dot\]|\(dot\)|\sdot\s)"
        r"\s*([a-zA-Z]{2,})",
        re.IGNORECASE,
    )

    PHONE_PATTERN = re.compile(
        r"""
        (?<!\d)
        (
            (?:\+?1[\s.-]?)?
            \(?\d{3}\)?
            [\s.-]?
            \d{3}
            [\s.-]?
            \d{4}
        )
        (?!\d)
        """,
        re.VERBOSE,
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
        """

        if not html or not html.strip():
            raise ValueError("HTML content cannot be empty.")

        # Keep a copy before removing script/style/etc.
        original_html = html

        soup = self._build_soup(html)

        emails = self._extract_emails(
            soup,
            original_html,
        )

        self._remove_junk(soup)

        text = self._extract_text(soup)

        phones = self._extract_phones(
            soup,
            text,
        )

        return {
            "text": text,
            "emails": emails,
            "phones": phones,
        }

    def _build_soup(self, html: str) -> BeautifulSoup:
        try:
            return BeautifulSoup(html, "lxml")
        except Exception:
            return BeautifulSoup(html, "html.parser")

    def _remove_junk(self, soup: BeautifulSoup) -> None:
        for tag in soup.find_all(self.REMOVE_TAGS):
            tag.decompose()

        for tag in soup.find_all(
            True,
            attrs={
                "style": lambda value: (
                    value
                    and "display:none"
                    in value.replace(" ", "").lower()
                )
            },
        ):
            tag.decompose()

        for tag in soup.find_all(
            True,
            attrs={"aria-hidden": "true"},
        ):
            tag.decompose()

    def _extract_text(self, soup: BeautifulSoup) -> str:
        text = soup.get_text(
            separator=" ",
            strip=True,
        )

        return re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

    def _extract_emails(
        self,
        soup: BeautifulSoup,
        html: str,
    ) -> list[str]:
        """
        Extract emails from multiple locations.

        Priority:

        1. mailto links
        2. normal HTML
        3. attributes
        4. obfuscated email formats
        """

        high_confidence = set()
        candidates = set()

        # --------------------------------------------------
        # 1. mailto links
        # --------------------------------------------------

        for tag in soup.find_all(
            "a",
            href=True,
        ):
            href = tag["href"].strip()

            if href.lower().startswith("mailto:"):
                email = (
                    href[7:]
                    .split("?", 1)[0]
                    .strip()
                    .lower()
                )

                if self._is_valid_email_candidate(email):
                    high_confidence.add(email)

        # --------------------------------------------------
        # 2. Normal email regex over original HTML
        # --------------------------------------------------

        for match in self.EMAIL_PATTERN.findall(html):
            candidates.add(
                html_lib.unescape(match).lower()
            )

        # --------------------------------------------------
        # 3. Search HTML attributes
        # --------------------------------------------------

        for tag in soup.find_all(True):
            for value in tag.attrs.values():

                if isinstance(value, list):
                    values = value
                else:
                    values = [value]

                for item in values:
                    if not isinstance(item, str):
                        continue

                    for match in self.EMAIL_PATTERN.findall(item):
                        candidates.add(
                            html_lib.unescape(
                                match
                            ).lower()
                        )

        # --------------------------------------------------
        # 4. Obfuscated emails
        # --------------------------------------------------

        for match in self.OBFUSCATED_EMAIL_PATTERN.findall(
            html_lib.unescape(html)
        ):
            email = (
                f"{match[0]}@{match[1]}.{match[2]}"
            ).lower()

            candidates.add(email)

        # --------------------------------------------------
        # Validate
        # --------------------------------------------------

        filtered = {
            email
            for email in candidates
            if self._is_valid_email_candidate(email)
        }

        result = sorted(high_confidence)

        for email in sorted(filtered):
            if email not in high_confidence:
                result.append(email)

        return result

    def _is_valid_email_candidate(
        self,
        email: str,
    ) -> bool:
        """
        Filter obvious third-party/tracking emails.
        """

        if not email:
            return False

        email = email.strip().lower()

        if "@" not in email:
            return False

        if email.count("@") != 1:
            return False

        local, domain = email.split("@", 1)

        if not local or not domain:
            return False

        if "." not in domain:
            return False

        if any(
            domain == ghost
            or domain.endswith("." + ghost)
            for ghost in self.GHOST_EMAIL_DOMAINS
        ):
            return False

        return True

    def _extract_phones(
        self,
        soup: BeautifulSoup,
        text: str,
    ) -> list[str]:
        """
        Extract phone numbers.

        tel: links receive priority.
        Visible-text regex provides fallback.
        """

        high_confidence = set()

        # --------------------------------------------------
        # 1. tel links
        # --------------------------------------------------

        for tag in soup.find_all(
            "a",
            href=True,
        ):
            href = tag["href"].strip()

            if href.lower().startswith("tel:"):
                phone = href[4:].strip()

                if (
                    phone
                    and not self._is_toll_free(phone)
                ):
                    high_confidence.add(phone)

        # --------------------------------------------------
        # 2. Visible text
        # --------------------------------------------------

        regex_phones = set(
            match.strip()
            for match in self.PHONE_PATTERN.findall(text)
        )

        filtered = {
            phone
            for phone in regex_phones
            if not self._is_toll_free(phone)
        }

        result = sorted(high_confidence)

        for phone in sorted(filtered):
            if phone not in high_confidence:
                result.append(phone)

        return result

    def _is_toll_free(
        self,
        phone: str,
    ) -> bool:
        normalized = re.sub(
            r"[^0-9]",
            "",
            phone,
        )

        # +1XXXXXXXXXX / 1XXXXXXXXXX
        if (
            len(normalized) == 11
            and normalized.startswith("1")
        ):
            normalized = normalized[1:]

        if len(normalized) < 10:
            return False

        area_code = normalized[:3]

        return area_code in self.TOLL_FREE_PREFIXES