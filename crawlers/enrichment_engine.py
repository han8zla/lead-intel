import asyncio
import random
from urllib.parse import urlparse

from playwright.async_api import (
    Page,
    async_playwright,
)

from core.models import RawLead
from utils.logger import get_logger


logger = get_logger(__name__)


class EnrichmentEngine:
    """
    Finds the actual business website from a supplied source URL.

    Responsibilities:
    - Start and manage Playwright.
    - Visit directory/source pages.
    - Find an external business website.
    - Return the enriched RawLead.

    This class does NOT:
    - Extract emails.
    - Extract phone numbers.
    - Parse HTML.
    - Save to the database.
    """

    UNSCRAPABLE_DOMAINS = {
        "zoominfo.com",
        "crunchbase.com",
        "linkedin.com",
        "facebook.com",
    }

    WEBSITE_SELECTORS = (
        'a:has-text("Visit Website")',
        'a:has-text("Business Website")',
        'a:has-text("Official Site")',
        'a:has-text("Website")',
        'a[href*="biz_redir"]',
        'a[data-testid="bizWebsiteLink"]',
    )

    USER_AGENT = (
        "Mozilla/5.0 "
        "(X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        min_delay: int = 10,
        max_delay: int = 20,
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay

        self.playwright = None
        self.browser = None
        self.context = None
        self.main_page: Page | None = None

    async def start(self) -> None:
        """Start Playwright and create the browser context."""

        self.playwright = await async_playwright().start()

        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        self.context = await self.browser.new_context(
            viewport={
                "width": 1920,
                "height": 1080,
            },
            user_agent=self.USER_AGENT,
        )

        self.main_page = await self.context.new_page()

        logger.info("Enrichment Engine started.")

    async def stop(self) -> None:
        """Safely shut down Playwright resources."""

        try:
            if self.context:
                await self.context.close()

        except Exception as exc:
            logger.warning(
                "Error closing browser context: %s",
                exc,
            )

        finally:
            self.context = None
            self.main_page = None

        try:
            if self.browser:
                await self.browser.close()

        except Exception as exc:
            logger.warning(
                "Error closing browser: %s",
                exc,
            )

        finally:
            self.browser = None

        try:
            if self.playwright:
                await self.playwright.stop()

        except Exception as exc:
            logger.warning(
                "Error stopping Playwright: %s",
                exc,
            )

        finally:
            self.playwright = None

        logger.info("Enrichment Engine closed.")

    async def _human_delay(self) -> None:
        """Wait for a randomized delay between operations."""

        delay = random.uniform(
            self.min_delay,
            self.max_delay,
        )

        logger.info(
            "Waiting %.1f seconds...",
            delay,
        )

        await asyncio.sleep(delay)

    @staticmethod
    def _domain(url: str) -> str:
        """Return a normalized domain."""

        return urlparse(url).netloc.lower().replace(
            "www.",
            "",
        )

    def _is_unscrapable(self, url: str) -> bool:
        """Check whether the source belongs to a known directory."""

        domain = self._domain(url)

        return any(
            blocked in domain
            for blocked in self.UNSCRAPABLE_DOMAINS
        )

    def _is_external_website(
        self,
        href: str,
        source_domain: str,
    ) -> bool:
        """Determine whether a link points outside the source domain."""

        if not href.startswith(("http://", "https://")):
            return False

        target_domain = self._domain(href)

        if not target_domain:
            return False

        if target_domain == source_domain:
            return False

        if "google.com" in target_domain:
            return False

        return True

    async def _find_website_link(
        self,
        page: Page,
        source_domain: str,
    ) -> str | None:
        """Look for a link leading to the business website."""

        for selector in self.WEBSITE_SELECTORS:
            try:
                links = await page.query_selector_all(
                    selector
                )

                for link in links:
                    href = await link.get_attribute("href")

                    if not href:
                        continue

                    if self._is_external_website(
                        href,
                        source_domain,
                    ):
                        logger.info(
                            "Found real website via [%s]: %s",
                            selector,
                            href,
                        )

                        return href

            except Exception as exc:
                logger.debug(
                    "Selector failed [%s]: %s",
                    selector,
                    exc,
                )

        return None

    async def _find_actual_website(
        self,
        start_url: str,
    ) -> str:
        """
        Visit a source URL and attempt to find the actual
        business website.
        """

        logger.info(
            "Visiting start URL to find website: %s",
            start_url,
        )

        if self._is_unscrapable(start_url):
            logger.warning(
                "Unscrapable directory detected: %s",
                self._domain(start_url),
            )

            return "UNSCRAPABLE"

        if self.context is None:
            raise RuntimeError(
                "Enrichment Engine has not been started."
            )

        source_domain = self._domain(start_url)

        page = await self.context.new_page()

        try:
            await page.goto(
                start_url,
                wait_until="domcontentloaded",
                timeout=20_000,
            )

            await asyncio.sleep(
                random.uniform(2, 4)
            )

            website = await self._find_website_link(
                page,
                source_domain,
            )

            if website:
                return website

            logger.info(
                "No directory exit door found. "
                "Assuming start URL is the actual website."
            )

            return start_url

        except Exception as exc:
            logger.warning(
                "Unable to inspect %s: %s",
                start_url,
                exc,
            )

            return start_url

        finally:
            await page.close()

    async def enrich_lead(
        self,
        lead: RawLead,
    ) -> RawLead:
        """Enrich a lead with its actual website."""

        logger.info(
            "Enriching lead: %s",
            lead.source_url,
        )

        if (
            lead.source_url
            and lead.source_url.startswith(
                ("http://", "https://")
            )
        ):
            lead.website = await self._find_actual_website(
                lead.source_url
            )

        await self._human_delay()

        return lead