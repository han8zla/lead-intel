import asyncio
import random
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Page
from utils.logger import get_logger
from core.models import RawLead

logger = get_logger(__name__)

class EnrichmentEngine:
    def __init__(self, min_delay: int = 10, max_delay: int = 20):
        self.min_delay = min_delay 
        self.max_delay = max_delay 
        self.browser = None
        self.context = None
        self.main_page = None

    async def start(self):
        self.playwright = await async_playwright().start()
        
        self.browser = await self.playwright.chromium.launch(
            headless=True, 
            args=[
                '--remote-debugging-port=9222',
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage'
            ]
        ) 
        
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        
        self.main_page = await self.context.new_page()
        await self.main_page.goto("about:blank")
        
        logger.info("Enrichment Engine started.")

    async def stop(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Enrichment Engine closed.")

    async def _human_delay(self):
        delay = random.uniform(self.min_delay, self.max_delay)
        logger.info(f"Waiting {delay:.1f} seconds...")
        await asyncio.sleep(delay)

    async def _find_actual_website(self, start_url: str) -> str:
        """Visits ANY link and tries to find the real business website exit door."""
        logger.info(f"Visiting start URL to find website: {start_url}")
        
        # Unscrapable domains - we just mark them so we don't waste time
        unscrapable_domains = ["zoominfo.com", "crunchbase.com", "linkedin.com", "facebook.com"]
        start_domain = urlparse(start_url).netloc.lower()
        
        for bad_domain in unscrapable_domains:
            if bad_domain in start_domain:
                logger.warning(f"Unscrapable directory detected: {bad_domain}. Aborting visit.")
                return "UNSCRAPABLE"

        page = await self.context.new_page()
        actual_website = None
        
        try:
            await page.goto(start_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(random.uniform(2, 4))

            # Universal selectors for "Go to real website"
            selectors = [
                'a:has-text("Visit Website")',
                'a:has-text("Business Website")',
                'a:has-text("Official Site")',
                'a:has-text("Website")',
                # Add Yelp-specific selectors just in case
                'a[href*="biz_redir"]', 
                'a[data-testid="bizWebsiteLink"]'
            ]

            for selector in selectors:
                try:
                    links = await page.query_selector_all(selector)
                    for link in links:
                        href = await link.get_attribute('href')
                        if href and href.startswith("http"):
                            link_domain = urlparse(href).netloc.replace("www.", "")
                            
                            # If the link goes to a DIFFERENT domain, we found the exit door!
                            if link_domain != start_domain.replace("www.", "") and "google.com" not in link_domain:
                                actual_website = href
                                logger.info(f"Found real website via [{selector}]: {actual_website}")
                                break
                except Exception:
                    pass # Ignore selector errors
                if actual_website:
                    break

            # If no exit door found, assume the start URL IS the website
            if not actual_website:
                logger.info("No directory exit door found. Assuming start URL is the actual website.")
                actual_website = start_url

        except Exception as e:
            logger.error(f"Error visiting start URL {start_url}: {e}")
            actual_website = start_url # Fallback to start URL even on error
        finally:
            await page.close()
            
        return actual_website

    async def enrich_lead(self, lead: RawLead) -> RawLead:
        logger.info(f"Enriching lead: {lead.source_url}")

        # We always start from the source URL provided by the user
        if lead.source_url and lead.source_url.startswith("http"):
            found_website = await self._find_actual_website(lead.source_url)
            lead.website = found_website
                
        await self._human_delay() 
        return lead