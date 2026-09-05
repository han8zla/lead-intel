import asyncio
from urllib.parse import urljoin, urlparse

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from processors.html_processor import HTMLProcessor
from utils.logger import get_logger

logger = get_logger(__name__)


class WebsiteProcessor:
    """Handles browser-based website fetching and HTML parsing."""

    SUBPAGE_KEYWORDS = ("contact", "about", "team", "service")
    COOKIE_SELECTORS = ("button:has-text('Accept')", "button:has-text('Accept All')", "button:has-text('I agree')", "button:has-text('Consent')", "a:has-text('Accept')")
    MAX_SUBPAGES = 3
    MAX_TEXT_LENGTH = 15000

    def __init__(self, page: Page | None):
        self.page = page
        self.html_processor = HTMLProcessor()

    def process_html(self, html: str) -> dict:
        return self.html_processor.process(html)

    async def _dismiss_cookies(self) -> None:
        if self.page is None:
            return
        for selector in self.COOKIE_SELECTORS:
            try:
                button = await self.page.query_selector(selector)
                if button:
                    await button.click()
                    await asyncio.sleep(1)
                    return
            except Exception:
                continue

    async def _safe_goto(self, url: str) -> None:
        if self.page is None:
            raise RuntimeError("Cannot navigate without a browser page.")
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except PlaywrightTimeoutError:
            logger.warning("Page load timed out for %s; continuing with partial load.", url)
        await asyncio.sleep(3)

    @staticmethod
    def _same_domain(base_url: str, target_url: str) -> bool:
        base_domain = urlparse(base_url).netloc.lower().removeprefix("www.")
        target_domain = urlparse(target_url).netloc.lower().removeprefix("www.")
        return base_domain == target_domain

    def _find_subpages(self, base_url: str, links) -> list[str]:
        priority_keywords = {"contact": 0, "about": 1, "team": 2, "service": 3}
        candidates: dict[str, int] = {}
        for link in links:
            href, text = link.get("href"), link.get("text", "")
            if not href:
                continue
            href = href.strip()
            if href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            full_url = urljoin(base_url, href)
            if not self._same_domain(base_url, full_url):
                continue
            combined = f"{href} {text}".lower()
            matched = [priority for keyword, priority in priority_keywords.items() if keyword in combined]
            if matched:
                candidates[full_url] = min(matched)
        return [url for url, _ in sorted(candidates.items(), key=lambda item: (item[1], item[0]))[: self.MAX_SUBPAGES]]

    @staticmethod
    def _merge_data(all_text, all_emails, all_phones, page_details, url, data):
        if data.get("text"):
            all_text.append(data["text"])
        all_emails.update(data.get("emails", []))
        all_phones.update(data.get("phones", []))
        page_details.append({
            "url": url,
            "features": data.get("features", {}),
            "emails": list(data.get("emails", [])),
            "phones": list(data.get("phones", [])),
            "text_preview": data.get("text", "")[:500],
        })

    async def scrape_page(self, url: str) -> dict:
        if self.page is None:
            raise RuntimeError("scrape_page() requires a Playwright page.")
        await self._safe_goto(url)
        await self._dismiss_cookies()
        html = await self.page.content()
        data = self.process_html(html)
        logger.info("Playwright extracted %s: emails=%d phones=%d text=%d", url, len(data.get("emails", [])), len(data.get("phones", [])), len(data.get("text", "")))
        return data

    async def scrape_website(self, base_url: str) -> dict:
        if self.page is None:
            raise RuntimeError("scrape_website() requires a Playwright page.")
        all_text, all_emails, all_phones, page_details = [], set(), set(), []
        pages = []
        try:
            homepage_data = await self.scrape_page(base_url)
            self._merge_data(all_text, all_emails, all_phones, page_details, base_url, homepage_data)
            pages.append(base_url)
            links = await self.page.query_selector_all("a")
            link_data = [{"href": await link.get_attribute("href"), "text": await link.inner_text()} for link in links]
            urls_to_visit = self._find_subpages(base_url, link_data)
            for url in urls_to_visit:
                try:
                    page_data = await self.scrape_page(url)
                    self._merge_data(all_text, all_emails, all_phones, page_details, url, page_data)
                    pages.append(url)
                except Exception as exc:
                    logger.warning("Failed to scrape subpage %s: %s", url, exc)
            return {
                "text": " ".join(all_text)[: self.MAX_TEXT_LENGTH],
                "emails": ", ".join(sorted(all_emails)),
                "phones": ", ".join(sorted(all_phones)),
                "pages": pages,
                "page_details": page_details,
            }
        except Exception:
            logger.exception("Fatal error scraping %s", base_url)
            return {"text": "", "emails": "", "phones": "", "pages": [], "page_details": []}
