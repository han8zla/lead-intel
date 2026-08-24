import logging

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

    Flow:

        URL
         |
         v
      HTTPX
         |
         v
    Quality Check
       /      \
    good      bad
     |          |
     v          v
    HTML      Playwright
     |          |
     +-----+----+
           |
           v
    HTMLProcessor
    """

    def __init__(
        self,
        page=None,
    ):
        self.page = page

        self.http_fetcher = HTTPFetcher()
        self.quality_checker = HTMLQualityChecker()

        # WebsiteProcessor already knows how to:
        # - process HTML
        # - use Playwright
        # - scrape useful subpages
        self.website_processor = WebsiteProcessor(
            page=page
        )

    async def ingest(self, url: str) -> dict:
        """
        Fetch and process a website.

        HTTP is attempted first.

        If HTTP returns usable HTML, that HTML is processed
        without starting another browser.

        If HTTP fails or returns a challenge/block page,
        the existing Playwright implementation is used.

        Returns:
            {
                "text": "...",
                "emails": "...",
                "phones": "...",
                "method": "http" or "playwright"
            }
        """

        logger.info(
            "Starting website ingestion: %s",
            url,
        )

        # -------------------------------------------------
        # STEP 1: Try normal HTTP
        # -------------------------------------------------

        try:
            logger.info(
                "Attempting HTTP fetch: %s",
                url,
            )

            html = await self.http_fetcher.fetch(url)

            quality = self.quality_checker.check(
                html
            )

            logger.info(
                "HTTP quality result for %s: usable=%s, reason=%s",
                url,
                quality.usable,
                quality.reason,
            )

            # -------------------------------------------------
            # STEP 2: HTTP succeeded
            # -------------------------------------------------

            if quality.usable:

                logger.info(
                    "Using HTTP result for %s",
                    url,
                )

                data = self.website_processor.process_html(
                    html
                )

                return {
                    "text": data["text"],
                    "emails": data["emails"],
                    "phones": data["phones"],
                    "method": "http",
                }

            # -------------------------------------------------
            # STEP 3: HTTP returned unusable HTML
            # -------------------------------------------------

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

        # -------------------------------------------------
        # STEP 4: Playwright fallback
        # -------------------------------------------------

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
            "emails": data["emails"],
            "phones": data["phones"],
            "method": "playwright",
        }