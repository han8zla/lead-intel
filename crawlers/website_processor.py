import asyncio
from urllib.parse import urljoin, urlparse

from playwright.async_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from processors.html_processor import HTMLProcessor
from utils.logger import get_logger


logger = get_logger(__name__)


class WebsiteProcessor:
    """Handles browser-based website fetching and HTML parsing."""

    SUBPAGE_KEYWORDS = (
        "contact",
        "about",
        "team",
        "service",
    )

    COOKIE_SELECTORS = (
        "button:has-text('Accept')",
        "button:has-text('Accept All')",
        "button:has-text('I agree')",
        "button:has-text('Consent')",
        "a:has-text('Accept')",
    )

    MAX_SUBPAGES = 3
    MAX_TEXT_LENGTH = 15000

    def __init__(self, page: Page | None):
        self.page = page
        self.html_processor = HTMLProcessor()

    def process_html(self, html: str) -> dict:
        """Parse raw HTML into structured lead data."""
        return self.html_processor.process(html)

    async def _dismiss_cookies(self) -> None:
        """Attempt to dismiss a common cookie-consent popup."""
        if self.page is None:
            return

        for selector in self.COOKIE_SELECTORS:
            try:
                button = await self.page.query_selector(selector)
                if button:
                    await button.click()
                    logger.info("Dismissed cookie consent popup.")
                    await asyncio.sleep(1)
                    return
            except Exception:
                continue

    async def _safe_goto(self, url: str) -> None:
        """Navigate while tolerating page-load timeouts."""
        if self.page is None:
            raise RuntimeError("Cannot navigate without a browser page.")

        try:
            await self.page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=15000,
            )
        except PlaywrightTimeoutError:
            logger.warning(
                "Page load timed out for %s; continuing with partial load.",
                url,
            )

        await asyncio.sleep(3)

    @staticmethod
    def _same_domain(base_url: str, target_url: str) -> bool:
        """Return True when both URLs belong to the same hostname."""
        base_domain = urlparse(base_url).netloc.lower().removeprefix("www.")
        target_domain = urlparse(target_url).netloc.lower().removeprefix("www.")
        return base_domain == target_domain

    def _find_subpages(self, base_url: str, links) -> list[str]:
        """Find and prioritize useful internal business pages."""
        priority_keywords = {
            "contact": 0,
            "about": 1,
            "team": 2,
            "service": 3,
        }

        candidates: dict[str, int] = {}

        for link in links:
            href = link.get("href")
            text = link.get("text", "")

            if not href:
                continue

            href = href.strip()
            if href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue

            full_url = urljoin(base_url, href)
            if not self._same_domain(base_url, full_url):
                continue

            combined = f"{href} {text}".lower()
            matched_priorities = [
                priority
                for keyword, priority in priority_keywords.items()
                if keyword in combined
            ]

            if matched_priorities:
                candidates[full_url] = min(matched_priorities)

        return [
            url
            for url, _ in sorted(
                candidates.items(),
                key=lambda item: (item[1], item[0]),
            )[: self.MAX_SUBPAGES]
        ]

    @staticmethod
    def _merge_data(
        all_text: list[str],
        all_emails: set[str],
        all_phones: set[str],
        data: dict,
    ) -> None:
        """Merge parsed page data into the accumulated result."""
        if data.get("text"):
            all_text.append(data["text"])
        all_emails.update(data.get("emails", []))
        all_phones.update(data.get("phones", []))

    async def scrape_page(self, url: str) -> dict:
        """Fetch one page with Playwright and parse its rendered HTML."""
        if self.page is None:
            raise RuntimeError("scrape_page() requires a Playwright page.")

        logger.info("Playwright fetching page: %s", url)
        await self._safe_goto(url)
        await self._dismiss_cookies()

        html = await self.page.content()
        data = self.process_html(html)

        logger.info(
            "Playwright extracted page %s: emails=%d phones=%d text=%d",
            url,
            len(data.get("emails", [])),
            len(data.get("phones", [])),
            len(data.get("text", "")),
        )

        return data

    async def scrape_website(self, base_url: str) -> dict:
        """Scrape the homepage and prioritized internal business pages."""
        if self.page is None:
            raise RuntimeError("scrape_website() requires a Playwright page.")

        logger.info("Deep scraping website: %s", base_url)

        all_text: list[str] = []
        all_emails: set[str] = set()
        all_phones: set[str] = set()

        try:
            homepage_data = await self.scrape_page(base_url)

            if len(homepage_data.get("text", "")) < 300:
                logger.warning(
                    "Homepage text is very short: %r",
                    homepage_data.get("text", "")[:200],
                )

            self._merge_data(
                all_text,
                all_emails,
                all_phones,
                homepage_data,
            )

            links = await self.page.query_selector_all("a")
            link_data = [
                {
                    "href": await link.get_attribute("href"),
                    "text": await link.inner_text(),
                }
                for link in links
            ]

            urls_to_visit = self._find_subpages(base_url, link_data)

            logger.info(
                "Found %d prioritized subpages: %s",
                len(urls_to_visit),
                urls_to_visit,
            )

            for url in urls_to_visit:
                try:
                    page_data = await self.scrape_page(url)
                    self._merge_data(
                        all_text,
                        all_emails,
                        all_phones,
                        page_data,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to scrape subpage %s: %s",
                        url,
                        exc,
                    )

            return {
                "text": " ".join(all_text)[: self.MAX_TEXT_LENGTH],
                "emails": ", ".join(sorted(all_emails)),
                "phones": ", ".join(sorted(all_phones)),
            }

        except Exception:
            logger.exception("Fatal error scraping %s", base_url)
            return {"text": "", "emails": "", "phones": ""}
