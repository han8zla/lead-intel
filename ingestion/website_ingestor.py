import logging
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ingestion.http_fetcher import (
    HTTPFetcher,
    HTTPFetchError,
)
from ingestion.html_quality import (
    HTMLQualityChecker,
)
from crawlers.website_processor import WebsiteProcessor


logger = logging.getLogger(__name__)


class WebsiteIngestor:
    """
    HTTP-first website ingestion with Playwright fallback.

    HTTP path:
        homepage
            ↓
        discover useful internal pages
            ↓
        fetch contact/about/services/team pages
            ↓
        HTMLProcessor

    Playwright path:
        WebsiteProcessor handles browser-based scraping.
    """

    MAX_SUBPAGES = 3

    SUBPAGE_KEYWORDS = (
        "contact",
        "about",
        "service",
        "team",
    )

    def __init__(self, page=None):
        self.page = page

        self.http_fetcher = HTTPFetcher()
        self.quality_checker = HTMLQualityChecker()

        self.website_processor = WebsiteProcessor(
            page=page
        )

    @staticmethod
    def _same_domain(base_url: str, target_url: str) -> bool:
        """Return True when both URLs belong to the same hostname."""

        base_domain = (
            urlparse(base_url)
            .netloc
            .lower()
            .removeprefix("www.")
        )

        target_domain = (
            urlparse(target_url)
            .netloc
            .lower()
            .removeprefix("www.")
        )

        return base_domain == target_domain

    def _find_subpages(
        self,
        base_url: str,
        html: str,
    ) -> list[str]:
        """
        Find useful internal business pages.

        Priority is given to contact/about/service/team pages.
        """

        soup = BeautifulSoup(
            html,
            "lxml",
        )

        found = []

        for tag in soup.find_all("a", href=True):
            href = tag.get("href")

            if not href:
                continue

            href = href.strip()

            if href.startswith((
                "#",
                "mailto:",
                "tel:",
                "javascript:",
            )):
                continue

            full_url = urljoin(
                base_url,
                href,
            )

            if not self._same_domain(
                base_url,
                full_url,
            ):
                continue

            combined = (
                f"{href} "
                f"{tag.get_text(' ', strip=True)}"
            ).lower()

            if any(
                keyword in combined
                for keyword in self.SUBPAGE_KEYWORDS
            ):
                found.append(full_url)

        # Preserve order while removing duplicates.
        unique_urls = []

        for url in found:
            if url not in unique_urls:
                unique_urls.append(url)

        return unique_urls[: self.MAX_SUBPAGES]

    @staticmethod
    def _merge_data(
        all_text: list[str],
        all_emails: set[str],
        all_phones: set[str],
        data: dict,
    ) -> None:
        """Merge page extraction results."""

        if data.get("text"):
            all_text.append(data["text"])

        all_emails.update(
            data.get("emails", [])
        )

        all_phones.update(
            data.get("phones", [])
        )

    async def _ingest_http_site(
        self,
        url: str,
        homepage_html: str,
    ) -> dict:
        """
        Process the homepage plus useful internal pages
        using HTTP only.
        """

        all_text = []
        all_emails = set()
        all_phones = set()

        # -------------------------------------------------
        # Homepage
        # -------------------------------------------------

        homepage_data = (
            self.website_processor.process_html(
                homepage_html
            )
        )

        self._merge_data(
            all_text,
            all_emails,
            all_phones,
            homepage_data,
        )

        # -------------------------------------------------
        # Discover useful internal pages
        # -------------------------------------------------

        subpages = self._find_subpages(
            url,
            homepage_html,
        )

        logger.info(
            "HTTP discovered %d useful subpages for %s: %s",
            len(subpages),
            url,
            subpages,
        )

        # -------------------------------------------------
        # Fetch subpages
        # -------------------------------------------------

        for subpage_url in subpages:

            try:
                logger.info(
                    "HTTP fetching subpage: %s",
                    subpage_url,
                )

                subpage_html = (
                    await self.http_fetcher.fetch(
                        subpage_url
                    )
                )

                quality = (
                    self.quality_checker.check(
                        subpage_html
                    )
                )

                if not quality.usable:
                    logger.warning(
                        "Skipping unusable subpage %s: %s",
                        subpage_url,
                        quality.reason,
                    )
                    continue

                subpage_data = (
                    self.website_processor.process_html(
                        subpage_html
                    )
                )

                self._merge_data(
                    all_text,
                    all_emails,
                    all_phones,
                    subpage_data,
                )

            except Exception as exc:
                logger.warning(
                    "Failed HTTP subpage %s: %s",
                    subpage_url,
                    exc,
                )

        return {
            "text": " ".join(all_text)[:15000],
            "emails": sorted(all_emails),
            "phones": sorted(all_phones),
            "method": "http",
        }

    async def ingest(self, url: str) -> dict:
        """
        Fetch and process a website.

        HTTP is attempted first.

        If HTTP succeeds:
            homepage + useful internal pages are processed.

        If HTTP fails or returns a challenge/block page:
            Playwright is used as fallback.
        """

        logger.info(
            "Starting website ingestion: %s",
            url,
        )

        # =================================================
        # STEP 1 — HTTP
        # =================================================

        try:
            logger.info(
                "Attempting HTTP fetch: %s",
                url,
            )

            html = await self.http_fetcher.fetch(
                url
            )

            quality = self.quality_checker.check(
                html
            )

            logger.info(
                "HTTP quality result for %s: usable=%s, reason=%s",
                url,
                quality.usable,
                quality.reason,
            )

            if quality.usable:

                logger.info(
                    "Using HTTP result for %s",
                    url,
                )

                return await self._ingest_http_site(
                    url,
                    html,
                )

            logger.warning(
                "HTTP HTML is not usable for %s: %s",
                url,
                quality.reason,
            )

        except HTTPFetchError as exc:

            logger.warning(
                "HTTP fetch failed for %s: %s",
                url,
                exc,
            )

        except Exception as exc:

            logger.exception(
                "Unexpected HTTP ingestion error for %s: %s",
                url,
                exc,
            )

        # =================================================
        # STEP 2 — Playwright fallback
        # =================================================

        logger.info(
            "Falling back to Playwright for %s",
            url,
        )

        if self.page is None:
            raise RuntimeError(
                "Playwright fallback requested, "
                "but no Playwright page was provided."
            )

        data = await self.website_processor.scrape_website(
            url
        )

        return {
            "text": data["text"],
            "emails": (
                data["emails"].split(", ")
                if data["emails"]
                else []
            ),
            "phones": (
                data["phones"].split(", ")
                if data["phones"]
                else []
            ),
            "method": "playwright",
        }