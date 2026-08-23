import asyncio
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.async_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from processors.html_processor import HTMLProcessor
from utils.logger import get_logger


logger = get_logger(__name__)


class WebsiteProcessor:
    """
    Transitional website processor.

    Responsibilities:
    - Browser-based fetching for the legacy worker.
    - Delegating HTML parsing to HTMLProcessor.

    IMPORTANT:
    The HTMLProcessor does not know anything about Playwright.
    """

    def __init__(self, page: Page | None):
        self.page = page
        self.html_processor = HTMLProcessor()

    def process_html(self, html: str) -> dict:
        """
        Public HTML-processing interface.

        This is the important new method.

        Any future ingestion method can call this:
        - HTTP
        - manual HTML
        - Playwright
        """

        return self.html_processor.process(html)

    async def _dismiss_cookies(self):
        """Legacy browser-only cookie handling."""

        if self.page is None:
            return

        cookie_selectors = [
            "button:has-text('Accept')",
            "button:has-text('Accept All')",
            "button:has-text('I agree')",
            "button:has-text('Consent')",
            "a:has-text('Accept')",
        ]

        for selector in cookie_selectors:
            try:
                button = await self.page.query_selector(selector)

                if button:
                    await button.click()

                    logger.info(
                        "Dismissed cookie consent popup."
                    )

                    await asyncio.sleep(1)
                    break

            except Exception:
                pass

    async def _safe_goto(self, url: str):
        """Legacy Playwright navigation."""

        if self.page is None:
            raise RuntimeError(
                "Cannot navigate without a browser page."
            )

        try:
            await self.page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=15000,
            )

        except PlaywrightTimeoutError:
            logger.warning(
                "Page load timed out for %s, "
                "continuing with partial load...",
                url,
            )

        await asyncio.sleep(3)

    async def scrape_website(self, base_url: str) -> dict:
        """
        Legacy Playwright scraping path.

        Parsing is now delegated to HTMLProcessor.
        """

        if self.page is None:
            raise RuntimeError(
                "scrape_website() requires a Playwright page."
            )

        logger.info(
            "Deep scraping website: %s",
            base_url,
        )

        all_text = []
        all_emails = set()
        all_phones = set()

        try:
            # Homepage
            await self._safe_goto(base_url)

            await self._dismiss_cookies()

            homepage_html = await self.page.content()

            homepage_data = self.process_html(
                homepage_html
            )

            if len(homepage_data["text"]) < 300:
                logger.warning(
                    "Homepage text is very short: %r",
                    homepage_data["text"][:200],
                )

            all_text.append(homepage_data["text"])
            all_emails.update(homepage_data["emails"])
            all_phones.update(homepage_data["phones"])

            # Find useful subpages.
            subpage_keywords = [
                "about",
                "contact",
                "service",
                "team",
            ]

            links = await self.page.query_selector_all("a")

            urls_to_visit = set()

            for link in links:
                href = await link.get_attribute("href")

                if not href:
                    continue

                full_url = urljoin(
                    base_url,
                    href,
                )

                if (
                    base_url in full_url
                    and any(
                        keyword in href.lower()
                        for keyword in subpage_keywords
                    )
                ):
                    urls_to_visit.add(full_url)

            urls_to_visit = list(urls_to_visit)[:3]

            logger.info(
                "Found %d subpages: %s",
                len(urls_to_visit),
                urls_to_visit,
            )

            # Subpages.
            for url in urls_to_visit:
                try:
                    logger.info(
                        "Scraping subpage: %s",
                        url,
                    )

                    await self._safe_goto(url)
                    await self._dismiss_cookies()

                    subpage_html = await self.page.content()

                    subpage_data = self.process_html(
                        subpage_html
                    )

                    all_text.append(
                        subpage_data["text"]
                    )

                    all_emails.update(
                        subpage_data["emails"]
                    )

                    all_phones.update(
                        subpage_data["phones"]
                    )

                except Exception as exc:
                    logger.warning(
                        "Failed to scrape subpage %s: %s",
                        url,
                        exc,
                    )

            final_text = " ".join(
                all_text
            )[:15000]

            return {
                "text": final_text,
                "emails": ", ".join(
                    sorted(all_emails)
                ),
                "phones": ", ".join(
                    sorted(all_phones)
                ),
            }

        except Exception as exc:
            logger.exception(
                "Fatal error scraping %s",
                base_url,
            )

            return {
                "text": "",
                "emails": "",
                "phones": "",
            }