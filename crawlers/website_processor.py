import asyncio
import re
from urllib.parse import urljoin
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
from utils.logger import get_logger

logger = get_logger(__name__)

class WebsiteProcessor:
    """Visits a website, dismisses popups, and deeply scrapes multiple pages."""

    def __init__(self, page: Page):
        self.page = page

    async def _dismiss_cookies(self):
        """Looks for and clicks common cookie consent buttons."""
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
                    logger.info("Dismissed cookie consent popup.")
                    await asyncio.sleep(1) 
                    break
            except Exception:
                pass 

    def _extract_data_from_html(self, html: str) -> dict:
        """Parses HTML using targeted extraction and aggressively bans tracking numbers."""
        soup = BeautifulSoup(html, 'lxml')
        
        # 1. DESTROY ALL JUNK before we even read the text
        for tag in soup.find_all(['script', 'style', 'noscript', 'iframe', 'svg']):
            tag.decompose()
        for tag in soup.find_all(True, attrs={'style': lambda x: x and 'display:none' in x.replace(' ', '').lower()}):
            tag.decompose()
        for tag in soup.find_all(True, attrs={'aria-hidden': 'true'}):
            tag.decompose()
            
        text = soup.get_text(separator=' ', strip=True)
        clean_text = re.sub(r'\s+', ' ', text).strip()
        
        # --- 1. EMAIL EXTRACTION (Hybrid) ---
        high_confidence_emails = set()
        for a_tag in soup.find_all('a', href=True):
            if a_tag['href'].startswith('mailto:'):
                email = a_tag['href'].replace('mailto:', '').split('?')[0].strip().lower()
                if email:
                    high_confidence_emails.add(email)
        
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        regex_emails = set(re.findall(email_pattern, html))
        ghost_domains = ['zendesk.com', 'intercom.com', 'drift.com', 'hubspot.com', 'facebook.com', 'google.com', 'sentry.io', 'example.com', 'email.com', 'yelp.com', 'squarespace.com', 'grammarly.com']
        
        filtered_regex_emails = set()
        for e in regex_emails:
            if not any(ghost in e.lower() for ghost in ghost_domains):
                filtered_regex_emails.add(e.lower())
                
        final_emails = list(high_confidence_emails) + [e for e in filtered_regex_emails if e not in high_confidence_emails]

        
        # --- 2. PHONE EXTRACTION (Strict Anti-Tracking) ---
        high_confidence_phones = set()
        for a_tag in soup.find_all('a', href=True):
            if a_tag['href'].startswith('tel:'):
                phone = a_tag['href'].replace('tel:', '').strip()
                if phone:
                    high_confidence_phones.add(phone)
        
        phone_pattern = r'(\+?1?\s*[-.\)]?\s*\(?\d{3}\)?\s*[-.\s]?\d{3}\s*[-.\s]?\d{4})'
        regex_phones = set(re.findall(phone_pattern, text))
        
        # THE IRONCLAD RULE: Ban Toll-Free Numbers (888, 800, 877, 866)
        toll_free_indicators = ['888', '800', '877', '866']
        
        filtered_regex_phones = set()
        for p in regex_phones:
            clean_p = p.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
            is_toll_free = any(clean_p.startswith(prefix) for prefix in toll_free_indicators)
            if not is_toll_free:
                filtered_regex_phones.add(p)
        
        filtered_high_conf_phones = set()
        for p in high_confidence_phones:
            clean_p = p.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
            is_toll_free = any(clean_p.startswith(prefix) for prefix in toll_free_indicators)
            if not is_toll_free:
                filtered_high_conf_phones.add(p)
                
        final_phones = list(filtered_high_conf_phones) + [p for p in filtered_regex_phones if p not in filtered_high_conf_phones]

        return {
            "text": clean_text,
            "emails": final_emails,
            "phones": final_phones
        }

    async def _safe_goto(self, url: str):
        """Tries to load a page, but if it times out, continues anyway with whatever loaded."""
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except PlaywrightTimeoutError:
            logger.warning(f"Page load timed out for {url}, but continuing with partial load...")
        
        # Give JS a few seconds to render regardless of how the load ended
        await asyncio.sleep(3)

    async def scrape_website(self, base_url: str) -> dict:
        logger.info(f"Deep scraping website: {base_url}")
        
        all_text = []
        all_emails = set()
        all_phones = set()

        try:
            # 1. Visit Homepage safely
            await self._safe_goto(base_url)
            
            # DEBUG: Take a picture
            try:
                await self.page.screenshot(path="debug_homepage.png", full_page=True)
            except Exception:
                pass # Screenshot can fail if page is weird, don't crash
            
            # 2. Dismiss Cookies!
            await self._dismiss_cookies()
            
            # 3. Extract Homepage Data
            homepage_html = await self.page.content()
            homepage_data = self._extract_data_from_html(homepage_html)
            
            if len(homepage_data["text"]) < 300:
                logger.warning(f"Homepage text is very short! Bot sees: '{homepage_data['text'][:200]}'")
            
            all_text.append(homepage_data["text"])
            all_emails.update(homepage_data["emails"])
            all_phones.update(homepage_data["phones"])
            
            # 4. Find Subpages
            subpage_keywords = ['about', 'contact', 'service', 'team']
            links = await self.page.query_selector_all('a')
            
            urls_to_visit = set()
            for link in links:
                href = await link.get_attribute('href')
                if href:
                    full_url = urljoin(base_url, href)
                    if base_url in full_url and any(kw in href.lower() for kw in subpage_keywords):
                        urls_to_visit.add(full_url)
            
            urls_to_visit = list(urls_to_visit)[:3]
            logger.info(f"Found {len(urls_to_visit)} subpages to visit: {urls_to_visit}")
            
            # 5. Visit Subpages safely
            for url in urls_to_visit:
                try:
                    logger.info(f"Scraping subpage: {url}")
                    await self._safe_goto(url)
                    await self._dismiss_cookies() 
                    
                    subpage_html = await self.page.content()
                    subpage_data = self._extract_data_from_html(subpage_html)
                    
                    all_text.append(subpage_data["text"])
                    all_emails.update(subpage_data["emails"])
                    all_phones.update(subpage_data["phones"])
                except Exception as e:
                    logger.warning(f"Failed to scrape subpage {url}: {e}")
            
            # 6. Combine everything
            combined_text = " ".join(all_text)
            final_text = combined_text[:15000]
            
            logger.info(f"Deep scrape complete. Found {len(all_emails)} emails, {len(all_phones)} phones. Text length: {len(final_text)}")
            
            return {
                "text": final_text,
                "emails": ", ".join(list(all_emails)),
                "phones": ", ".join(list(all_phones))
            }

        except Exception as e:
            logger.error(f"Fatal error deep scraping {base_url}: {e}")
            return {"text": "", "emails": "", "phones": ""}