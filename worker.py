import asyncio
import hashlib
import json

from crawlers.enrichment_engine import EnrichmentEngine
from ingestion.website_ingestor import WebsiteIngestor
from processors.business_analyzer import BusinessAnalyzer
from core.database import Database
from core.intelligence_store import IntelligenceStore
from core.models import RawLead
from observability.audit import AuditTrail
from utils.logger import get_logger
from utils.google_sheets import GoogleSheetsManager
from ai.email_personalizer import EmailPersonalizer


logger = get_logger(__name__)


def _hash_payload(payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _record_page_details(store: IntelligenceStore, run_id: str, page_details: list) -> None:
    for page in page_details or []:
        if not isinstance(page, dict):
            continue
        url = page.get("url") or page.get("page_url")
        if not url:
            continue
        store.record_page(
            run_id,
            url,
            status=page.get("status", page.get("status_code", "UNKNOWN")),
            method=page.get("method"),
            content_length=page.get("content_length") or page.get("length"),
            error_type=page.get("error_type"),
            error_message=page.get("error") or page.get("error_message"),
            metadata={k: v for k, v in page.items() if k not in {"url", "page_url", "method", "status", "status_code", "content_length", "length", "error_type", "error", "error_message"}},
        )


async def main():
    db = Database()
    db.setup_tables()

    intelligence = IntelligenceStore()
    intelligence.setup_tables()
    audit = AuditTrail(intelligence)

    engine = EnrichmentEngine(min_delay=5, max_delay=10)
    analyzer = BusinessAnalyzer()
    personalizer = EmailPersonalizer()

    logger.info("Starting Worker...")
    logger.info("AI personalization available: %s", personalizer.router.available)
    logger.info("Configured AI models: %s", personalizer.router.models())
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
            run_id = intelligence.start_run(lead_id, source_url)
            audit.event(run_id, lead_id, "analysis.started", stage="analysis", source_url=source_url)
            logger.info("Picked up Lead ID %s: %s (run_id=%s)", lead_id, source_url, run_id)
            db.update_lead_status(lead_id, "PROCESSING")

            lead = RawLead(
                company_name=lead_row["company_name"] or "",
                location=lead_row["location"] or "",
                source_url=source_url,
                source="manual_link",
            )

            try:
                audit.event(run_id, lead_id, "crawl.started", stage="crawl", source_url=source_url)
                enriched_lead = await engine.enrich_lead(lead)
                final_website = enriched_lead.website or "NOT_FOUND"
                audit.event(
                    run_id,
                    lead_id,
                    "crawl.enrichment_completed",
                    stage="crawl",
                    website=final_website,
                    company_name=enriched_lead.company_name,
                )
                db.update_lead_status(
                    lead_id,
                    "ENRICHED",
                    website=final_website,
                    company_name=enriched_lead.company_name,
                )

                scraped_data = {
                    "text": "",
                    "emails": [],
                    "phones": [],
                    "pages": [],
                    "page_details": [],
                    "method": "none",
                }
                if final_website != "NOT_FOUND":
                    logger.info("Starting website ingestion for Lead ID %s...", lead_id)
                    audit.event(run_id, lead_id, "crawl.ingestion_started", stage="crawl", website=final_website)
                    scraped_data = await ingestor.ingest(final_website)

                _record_page_details(intelligence, run_id, scraped_data.get("page_details", []))
                audit.event(
                    run_id,
                    lead_id,
                    "crawl.completed",
                    stage="crawl",
                    pages=len(scraped_data.get("pages", [])),
                    method=scraped_data.get("method", "unknown"),
                    text_length=len(scraped_data.get("text", "")),
                    emails=len(scraped_data.get("emails", [])),
                    phones=len(scraped_data.get("phones", [])),
                )

                db.update_lead_scraped_data(
                    lead_id,
                    emails=", ".join(scraped_data["emails"]),
                    phones=", ".join(scraped_data["phones"]),
                    text=scraped_data["text"],
                )

                audit.event(run_id, lead_id, "extraction.completed", stage="extraction")
                for page in scraped_data.get("page_details", []):
                    dom = page.get("dom") or {}
                    if not dom:
                        continue
                    page_url = page.get("url")
                    compact_dom = {
                        "metadata": dom.get("metadata", {}),
                        "headings": dom.get("headings", {}),
                        "links": dom.get("links", []),
                        "buttons": dom.get("buttons", []),
                        "forms": dom.get("forms", []),
                        "json_ld": dom.get("json_ld", []),
                        "technologies": dom.get("technologies", []),
                        "external_domains": dom.get("external_domains", []),
                        "attribute_samples": dom.get("attribute_samples", []),
                    }
                    intelligence.record_observation(
                        run_id,
                        page_url=page_url,
                        kind="dom_profile",
                        key="page_intelligence",
                        value=compact_dom,
                        evidence={"source": "HTMLProcessor", "page": page_url},
                        confidence=1.0,
                    )
                    audit.event(
                        run_id,
                        lead_id,
                        "dom.observed",
                        stage="extraction",
                        page=page_url,
                        links=len(dom.get("links", [])),
                        forms=len(dom.get("forms", [])),
                        buttons=len(dom.get("buttons", [])),
                        technologies=len(dom.get("technologies", [])),
                        external_domains=len(dom.get("external_domains", [])),
                    )

                analysis = analyzer.analyze(
                    final_website,
                    text=scraped_data.get("text", ""),
                    scraped_data=scraped_data,
                )
                audit.event(
                    run_id,
                    lead_id,
                    "signals.analyzed",
                    stage="signals",
                    signal_count=sum(1 for value in analysis.get("signals", {}).values() if value),
                )

                for signal_name, signal_value in analysis.get("signals", {}).items():
                    if signal_value:
                        intelligence.record_signal(
                            run_id,
                            name=signal_name,
                            classification="KNOWN",
                            confidence=1.0,
                            evidence=[{"source": "business_analyzer", "value": signal_value}],
                            context={"industry": analysis.get("industry", "unknown")},
                        )
                        audit.event(
                            run_id,
                            lead_id,
                            "signal.created",
                            stage="signals",
                            signal=signal_name,
                            classification="KNOWN",
                        )

                analysis["business_intelligence"] = analyzer.opportunity_detector.analyze_business(
                    signals=analysis["signals"],
                    text=scraped_data.get("text", ""),
                    pages=scraped_data.get("pages", []),
                    industry=analysis["industry"],
                    services=analysis.get("services", []),
                )
                audit.event(
                    run_id,
                    lead_id,
                    "business_intelligence.completed",
                    stage="intelligence",
                    industry=analysis["industry"],
                    audience_count=len(analysis["business_intelligence"].get("business_profile", {}).get("audiences", [])),
                )

                logger.info(
                    "Business Analysis: business=%s industry=%s score=%s",
                    analysis["business_name"],
                    analysis["industry"],
                    analysis["opportunity_score"],
                )
                logger.info("Business Signals: %s", analysis["signals"])
                logger.info("Business Intelligence: %s", analysis["business_intelligence"])

                for opportunity in analysis["opportunities"]:
                    intelligence.record_opportunity(run_id, opportunity)
                    audit.event(
                        run_id,
                        lead_id,
                        "opportunity.created",
                        stage="opportunity",
                        opportunity_type=opportunity.get("type"),
                        title=opportunity.get("title"),
                        score=opportunity.get("score"),
                        confidence=opportunity.get("confidence"),
                    )
                    logger.info(
                        "Opportunity [%s] %s: %s (confidence=%s)",
                        opportunity["priority"].upper(),
                        opportunity["title"],
                        opportunity.get("recommendation", ""),
                        opportunity["confidence"],
                    )

                audit.event(
                    run_id,
                    lead_id,
                    "score.calculated",
                    stage="scoring",
                    score=analysis["opportunity_score"],
                    opportunity_count=len(analysis["opportunities"]),
                )

                if personalizer.router.available and analysis["opportunities"]:
                    audit.event(run_id, lead_id, "ai.personalization.started", stage="ai")
                    try:
                        draft = await personalizer.generate(analysis=analysis)
                        analysis["personalized_email"] = draft
                        if personalizer.last_response:
                            analysis["ai_provider"] = personalizer.last_response.provider
                            analysis["ai_model"] = personalizer.last_response.model
                            intelligence.record_ai(
                                run_id,
                                purpose="outreach_draft",
                                provider=personalizer.last_response.provider,
                                model=personalizer.last_response.model,
                                input_hash=_hash_payload({"opportunities": analysis["opportunities"]}),
                                status="COMPLETED",
                                input_summary={
                                    "business_name": analysis.get("business_name"),
                                    "opportunity_count": len(analysis["opportunities"]),
                                },
                                output={"draft": draft},
                            )
                            audit.event(
                                run_id,
                                lead_id,
                                "ai.personalization.completed",
                                stage="ai",
                                provider=personalizer.last_response.provider,
                                model=personalizer.last_response.model,
                            )
                    except Exception as ai_exc:
                        analysis["personalized_email_error"] = str(ai_exc)
                        intelligence.record_ai(
                            run_id,
                            purpose="outreach_draft",
                            provider=None,
                            model=None,
                            input_hash=_hash_payload({"opportunities": analysis["opportunities"]}),
                            status="FAILED",
                            input_summary={
                                "business_name": analysis.get("business_name"),
                                "opportunity_count": len(analysis["opportunities"],
                            },
                            error_message=str(ai_exc),
                        )
                        audit.event(
                            run_id,
                            lead_id,
                            "ai.personalization.failed",
                            stage="ai",
                            severity="WARNING",
                            error_type=type(ai_exc).__name__,
                        )
                        logger.warning("AI personalization failed for Lead ID %s: %s", lead_id, ai_exc)

                db.update_lead_analysis(
                    lead_id,
                    opportunity_score=analysis["opportunity_score"],
                    opportunity_data=json.dumps(analysis),
                )

                final_status = "MISSING_DATA" if not scraped_data["emails"] and not scraped_data["phones"] else "COMPLETED"
                db.update_lead_status(lead_id, final_status, website=final_website)
                sheets_manager.add_lead(
                    lead_id=lead_id,
                    company_name=enriched_lead.company_name or analysis["business_name"] or "Unknown",
                    source_url=source_url,
                    website=final_website,
                    emails=scraped_data["emails"],
                    phones=scraped_data["phones"],
                    status=final_status,
                    text=scraped_data["text"],
                    opportunity_score=analysis["opportunity_score"],
                )

                intelligence.finish_run(
                    run_id,
                    "COMPLETED",
                    {
                        "status": final_status,
                        "pages": len(scraped_data.get("pages", [])),
                        "signals": sum(1 for value in analysis.get("signals", {}).values() if value),
                        "opportunities": len(analysis.get("opportunities", [])),
                        "score": analysis.get("opportunity_score"),
                    },
                )
                audit.event(
                    run_id,
                    lead_id,
                    "analysis.completed",
                    stage="analysis",
                    status=final_status,
                    score=analysis["opportunity_score"],
                )
                logger.info(
                    "Finished Lead ID %s. Status: %s. Opportunity score: %s (run_id=%s)",
                    lead_id,
                    final_status,
                    analysis["opportunity_score"],
                    run_id,
                )

            except Exception as exc:
                intelligence.fail_run(run_id, type(exc).__name__, str(exc))
                audit.event(
                    run_id,
                    lead_id,
                    "analysis.failed",
                    stage="analysis",
                    severity="ERROR",
                    message=str(exc),
                    error_type=type(exc).__name__,
                )
                logger.exception("Failed Lead ID %s (run_id=%s): %s", lead_id, run_id, exc)
                db.update_lead_status(lead_id, "FAILED", website="ERROR")

    finally:
        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
