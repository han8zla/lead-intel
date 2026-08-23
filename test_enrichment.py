import asyncio
from crawlers.enrichment_engine import EnrichmentEngine
from core.models import RawLead
from utils.logger import get_logger

logger = get_logger(__name__)

async def main():
    logger.info("Starting Test Script...")
    
    # Initialize engine with short delays for testing
    engine = EnrichmentEngine(min_delay=5, max_delay=10)
    
    await engine.start()
    
    # Give you a moment to connect the SSH tunnel
    logger.info("Browser launched! You have 30 seconds to setup your SSH tunnel and Chrome Inspector...")
    await asyncio.sleep(120)
    
    try:
        # Test Lead
        lead1 = RawLead(company_name="Downtown Dental", location="Chicago", source="manual")
        
        logger.info(f"Processing lead: {lead1.company_name}")
        enriched1 = await engine.enrich_lead(lead1)
        
        logger.info(f"FINISHED! Website found: {enriched1.website}")
        
    finally:
        await engine.stop()

if __name__ == "__main__":
    asyncio.run(main())