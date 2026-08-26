import asyncio
import json

from crawlers.enrichment_engine import EnrichmentEngine
from ingestion.website_ingestor import WebsiteIngestor
from processors.business_analyzer import BusinessAnalyzer
from core.database import Database
from core.models import RawLead
from utils.logger import get_logger
from utils.google_sheets import GoogleSheetsManager


logger = get_logger(__name__)


async def main():
    db = Database()
    db.setup_tables()
    engine = EnrichmentEngine(min_delay=5, max_delay=10)
    analyzer = BusinessAnalyzer()

    logger.info("Starting Worker...")

    await engine.start()

    ingestor = WebsiteIngestor(engine.main_page)
    sheets_manager = GoogleSheetsManager()

    try:
        while True:
            lead_row = db.get_next_pending()

            if not lead_row:
                await asyncio.sleep(10)
                continue

            lead_id = lead_row["id"]
            source_url = lead_row["source_url"]

            logger.info("Picked up Lead ID %s: %s", lead_id, source_url)
            db.update_lead_status(lead_id, "PROCESSING")

            lead = RawLead(
                company_name=lead_row["company_name"] or "",
                location=lead_row["location"] or "",
                source_url=source_url,
                source="manual_link",
            )

            try:
                enriched_lead = await engine.enrich_lead(lead)
                final_website = enriched_lead.website or "NOT_FOUND"

                db.update_lead_status(
                    lead_id,
                    "ENRICHED",
                    website=final_website,
                    company_name=enriched_lead.company_name,
                )

                scraped_data = {"text": "", "emails": [], "phones": [], "method": "none"}

                if final_website != "NOT_FOUND":
                    logger.info("Starting website ingestion for Lead ID %s...", lead_id)
                    scraped_data = await ingestor.ingest(final_website)

                db.update_lead_scraped_data(
                    lead_id,
                    emails=", ".join(scraped_data["emails"]),
                    phones=", ".join(scraped_data["phones"]),
                    text=scraped_data["text"],
                )

                # Analyze the captured website content. The analyzer is deterministic
                # and creates a transparent baseline for the later AI opportunity layer.
                analysis = analyzer.analyze(
                    final_website,
                    scraped_data.get("text", ""),
                    scraped_data.get("text", ""),
                )
                db.update_lead_analysis(
                    lead_id,
                    opportunity_score=analysis["opportunity_score"],
                    opportunity_data=json.dumps(analysis),
                )

                if not scraped_data["emails"] and not scraped_data["phones"]:
                    final_status = "MISSING_DATA"
                else:
                    final_status = "COMPLETED"

                db.update_lead_status(
                    lead_id,
                    final_status,
                    website=final_website,
                )

                sheets_manager.add_lead(
                    lead_id=lead_id,
                    company_name=enriched_lead.company_name or "Unknown",
                    source_url=source_url,
                    website=final_website,
                    emails=scraped_data["emails"],
                    phones=scraped_data["phones"],
                    status=final_status,
                    text=scraped_data["text"],
                )

                logger.info(
                    "Finished Lead ID %s. Status: %s. Opportunity score: %s",
                    lead_id,
                    final_status,
                    analysis["opportunity_score"],
                )

            except Exception as exc:
                logger.exception("Failed Lead ID %s: %s", lead_id, exc)
                db.update_lead_status(lead_id, "FAILED", website="ERROR")

    finally:
        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
