import asyncio
from crawlers.enrichment_engine import EnrichmentEngine
from crawlers.website_processor import WebsiteProcessor
from core.database import Database
from core.models import RawLead
from utils.logger import get_logger
from utils.google_sheets import GoogleSheetsManager

logger = get_logger(__name__)

async def main():
    db = Database()
    engine = EnrichmentEngine(min_delay=5, max_delay=10) 
    processor = None 
    
    logger.info("Starting Worker...")
    await engine.start()
    processor = WebsiteProcessor(engine.main_page)
    sheets_manager = GoogleSheetsManager()
    
    try:
        while True:
            lead_row = db.get_next_pending()
            
            if not lead_row:
                await asyncio.sleep(10)
                continue
            
            lead_id = lead_row['id']
            source_url = lead_row['source_url']
            
            logger.info(f"Picked up Lead ID {lead_id}: {source_url}")
            db.update_lead_status(lead_id, "PROCESSING")
            
            lead = RawLead(
                company_name=lead_row['company_name'] or "",
                location=lead_row['location'] or "",
                source_url=source_url,
                source="manual_link"
            )
            
            try:
                # STEP 1: Find the actual website URL
                enriched_lead = await engine.enrich_lead(lead)
                final_website = enriched_lead.website or "NOT_FOUND"
                
                db.update_lead_status(lead_id, "ENRICHED", website=final_website, company_name=enriched_lead.company_name)
                logger.info(f"✅ Enriched Lead ID {lead_id}. Website: {final_website}")
                
                # STEP 2: Scrape the final website
                scraped_data = {"text": "", "emails": "", "phones": ""}
                
                if final_website != "NOT_FOUND":
                    logger.info(f"Starting scrape for Lead ID {lead_id}...")
                    scraped_data = await processor.scrape_website(final_website)
                
                # Save the data
                db.update_lead_scraped_data(
                    lead_id,
                    emails=scraped_data["emails"],
                    phones=scraped_data["phones"],
                    text=scraped_data["text"]
                )
                
                # Determine Status: If no email AND no phone, mark as MISSING_DATA
                if not scraped_data["emails"] and not scraped_data["phones"]:
                    final_status = "MISSING_DATA"
                else:
                    final_status = "COMPLETED"
                
                db.update_lead_status(lead_id, final_status, website=final_website)
                logger.info(f"✅ Finished Lead ID {lead_id}. Status: {final_status}")
                
                # Push to Google Sheets!
                sheets_manager.add_lead(
                    lead_id=lead_id,
                    company_name=enriched_lead.company_name or "Unknown",
                    source_url=source_url,
                    website=final_website,
                    emails=scraped_data["emails"],
                    phones=scraped_data["phones"],
                    status=final_status
                )

            except Exception as e:
                logger.error(f"❌ Failed Lead ID {lead_id}: {e}")
                db.update_lead_status(lead_id, "FAILED", website="ERROR")
                
    finally:
        await engine.stop()

if __name__ == "__main__":
    asyncio.run(main())