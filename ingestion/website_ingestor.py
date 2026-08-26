import logging
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ingestion.http_fetcher import HTTPFetcher, HTTPFetchError
from ingestion.html_quality import HTMLQualityChecker
from crawlers.website_processor import WebsiteProcessor

logger = logging.getLogger(__name__)


class WebsiteIngestor:
    """HTTP-first website ingestion with per-page browser fallback."""

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
        self.website_processor = WebsiteProcessor(page=page)

    @staticmethod
    def _same_domain(base_url: str, target_url: str) -> bool:
        base_domain = urlparse(base_url).netloc.lower().removeprefix("www.")
        target_domain = urlparse(target_url).netloc.lower().removeprefix("www.")
        return base_domain == target_domain

    def _find_subpages(self, base_url: str, html: str) -> list[str]:
        """Find useful internal pages, prioritizing contact pages."""
        soup = BeautifulSoup(html, "lxml")
        priority = {"contact": 0, "about": 1, "team": 2, "service": 3}
        candidates: dict[str, int] = {}

        for tag in soup.find_all("a", href=True):
            href = tag.get("href", "").strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue

            full_url = urljoin(base_url, href)
            if not self._same_domain(base_url, full_url):
                continue

            combined = f"{href} {tag.get_text(' ', strip=True)}".lower()
            priorities = [p for keyword, p in priority.items() if keyword in combined]
            if priorities:
                candidates[full_url] = min(priorities)

        return [
            url for url, _ in sorted(
                candidates.items(), key=lambda item: (item[1], item[0])
            )[: self.MAX_SUBPAGES]
        ]

    @staticmethod
    def _merge_data(all_text, all_emails, all_phones, data):
        if data.get("text"):
            all_text.append(data["text"])
        all_emails.update(data.get("emails", []))
        all_phones.update(data.get("phones", []))

    async def _ingest_http_site(self, url: str, homepage_html: str) -> dict:
        all_text = []
        all_emails = set()
        all_phones = set()
        pages = []

        homepage_data = self.website_processor.process_html(homepage_html)
        self._merge_data(all_text, all_emails, all_phones, homepage_data)
        pages.append(url)

        subpages = self._find_subpages(url, homepage_html)
        logger.info(
            "HTTP discovered %d prioritized subpages for %s: %s",
            len(subpages), url, subpages,
        )

        used_playwright = False

        for subpage_url in subpages:
            try:
                logger.info("HTTP fetching subpage: %s", subpage_url)
                subpage_html = await self.http_fetcher.fetch(subpage_url)
                quality = self.quality_checker.check(subpage_html)

                if quality.usable:
                    subpage_data = self.website_processor.process_html(subpage_html)
                    self._merge_data(all_text, all_emails, all_phones, subpage_data)
                    pages.append(subpage_url)
                    continue

                logger.warning(
                    "HTTP subpage unusable: %s: %s",
                    subpage_url, quality.reason,
                )

                if self.page is None:
                    logger.warning(
                        "No Playwright page available; cannot recover subpage %s",
                        subpage_url,
                    )
                    continue

                logger.info(
                    "Falling back to Playwright for subpage: %s",
                    subpage_url,
                )
                subpage_data = await self.website_processor.scrape_page(subpage_url)
                self._merge_data(all_text, all_emails, all_phones, subpage_data)
                pages.append(subpage_url)
                used_playwright = True

            except Exception as exc:
                logger.warning("Failed to ingest subpage %s: %s", subpage_url, exc)

        return {
            "text": " ".join(all_text)[:15000],
            "emails": sorted(all_emails),
            "phones": sorted(all_phones),
            "pages": pages,
            "method": "http+playwright" if used_playwright else "http",
        }

    async def ingest(self, url: str) -> dict:
        logger.info("Starting website ingestion: %s", url)

        try:
            logger.info("Attempting HTTP fetch: %s", url)
            html = await self.http_fetcher.fetch(url)
            quality = self.quality_checker.check(html)

            logger.info(
                "HTTP quality result for %s: usable=%s, reason=%s",
                url, quality.usable, quality.reason,
            )

            if quality.usable:
                logger.info("Using HTTP result for %s", url)
                return await self._ingest_http_site(url, html)

            logger.warning(
                "HTTP HTML is not usable for %s: %s",
                url, quality.reason,
            )

        except HTTPFetchError as exc:
            logger.warning("HTTP fetch failed for %s: %s", url, exc)
        except Exception as exc:
            logger.exception("Unexpected HTTP ingestion error for %s", url)

        logger.info("Falling back to Playwright for %s", url)

        if self.page is None:
            raise RuntimeError(
                "Playwright fallback requested, but no Playwright page was provided."
            )

        data = await self.website_processor.scrape_website(url)
        return {
            "text": data["text"],
            "emails": data["emails"].split(", ") if data["emails"] else [],
            "phones": data["phones"].split(", ") if data["phones"] else [],
            "pages": data.get("pages", []),
            "method": "playwright",
        }
