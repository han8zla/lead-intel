import json

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ai.provider_registry import AIProviderRegistry
from core.database import Database
from core.intelligence_store import IntelligenceStore
from core.unknown_signal_registry import UnknownSignalRegistry
from crawlers.website_processor import WebsiteProcessor
from utils.google_sheets import GoogleSheetsManager
from utils.logger import get_logger


logger = get_logger(__name__)


app = FastAPI()
templates = Jinja2Templates(directory="templates")
db = Database()
db.setup_tables()
intelligence = IntelligenceStore(db.db_path)
intelligence.setup_tables()
signal_registry = UnknownSignalRegistry(db.db_path)
signal_registry.setup_tables()
ai_registry = AIProviderRegistry(db.db_path)
ai_registry.setup_tables()
sheets_manager = GoogleSheetsManager()


def _decode_analysis(lead):
    raw_analysis = lead.get("opportunity_data")
    if raw_analysis:
        try:
            lead["analysis"] = json.loads(raw_analysis)
        except (TypeError, json.JSONDecodeError):
            lead["analysis"] = None
    else:
        lead["analysis"] = None
    lead.pop("opportunity_data", None)
    return lead


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {"request": request})


@app.get("/signals", response_class=HTMLResponse)
async def signals_page(request: Request):
    return templates.TemplateResponse(request, "signals.html", {"request": request})


@app.get("/settings/ai", response_class=HTMLResponse)
async def ai_settings(request: Request):
    return templates.TemplateResponse(request, "ai_settings.html", {"request": request})


@app.get("/api/dashboard")
async def dashboard_data():
    """Return dashboard metrics and recent lead analysis."""
    leads = [_decode_analysis(lead) for lead in db.get_dashboard_leads()]
    return {
        "success": True,
        "stats": db.get_dashboard_stats(),
        "leads": leads,
    }


@app.get("/api/leads/{lead_id}")
async def lead_detail(lead_id: int):
    """Return one complete lead and its stored intelligence."""
    lead = db.get_lead(lead_id)
    if not lead:
        return {"success": False, "message": "Lead not found."}
    return {"success": True, "lead": _decode_analysis(lead)}


@app.get("/api/intelligence/unknowns")
async def intelligence_unknowns(status: str | None = None):
    """Return reviewable unknown observations and their AI interpretations."""
    allowed = {None, "PENDING", "VALIDATED", "REJECTED", "KEPT_UNKNOWN"}
    if status not in allowed:
        return {"success": False, "message": "Invalid validation status."}
    return {"success": True, "unknowns": intelligence.list_unknowns(status)}


@app.get("/api/intelligence/signals")
async def intelligence_signals():
    """Return the reusable, human-validated signal library."""
    return {"success": True, "signals": signal_registry.list_signals()}


@app.post("/api/intelligence/unknowns/{unknown_id}/validate")
async def validate_unknown_signal(unknown_id: int):
    """Human approval gate: validate an unknown and promote it to the reusable signal library."""
    unknown = intelligence.get_unknown(unknown_id)
    if not unknown:
        return {"success": False, "message": "Unknown signal not found."}
    if unknown["validation_status"] == "VALIDATED":
        return {"success": True, "message": "Signal is already validated.", "signal": signal_registry.get_by_fingerprint(unknown["fingerprint"])}

    interpretation = unknown.get("interpretation") or {}
    name = interpretation.get("canonical_name") or unknown.get("observation", {}).get("unknown_workflow")
    if not name:
        return {"success": False, "message": "A signal name is required before validation."}

    signal_id = signal_registry.promote(
        fingerprint=unknown["fingerprint"],
        name=name,
        description=interpretation.get("business_meaning"),
        pattern={
            "observation": unknown.get("observation") or {},
            "context": unknown.get("context") or {},
            "ai_interpretation": interpretation,
        },
        validation_source="human_dashboard",
    )
    intelligence.update_unknown(unknown_id, validation_status="VALIDATED")
    return {
        "success": True,
        "message": "Signal validated and added to the reusable signal library.",
        "signal": signal_registry.get_by_fingerprint(unknown["fingerprint"]),
        "signal_id": signal_id,
    }


@app.post("/api/intelligence/unknowns/{unknown_id}/reject")
async def reject_unknown_signal(unknown_id: int):
    """Human review action: reject the interpretation without deleting the evidence."""
    unknown = intelligence.get_unknown(unknown_id)
    if not unknown:
        return {"success": False, "message": "Unknown signal not found."}
    intelligence.update_unknown(unknown_id, validation_status="REJECTED")
    return {"success": True, "message": "Unknown signal rejected. Evidence remains in the analysis history."}


@app.post("/api/intelligence/unknowns/{unknown_id}/keep")
async def keep_unknown_signal(unknown_id: int):
    """Keep an observation as evidence without promoting it to the reusable library."""
    unknown = intelligence.get_unknown(unknown_id)
    if not unknown:
        return {"success": False, "message": "Unknown signal not found."}
    intelligence.update_unknown(unknown_id, validation_status="KEPT_UNKNOWN")
    return {"success": True, "message": "Observation preserved as unknown evidence; it was not promoted."}


@app.get("/api/ai/providers")
async def ai_providers():
    """Return configured AI providers without exposing API keys."""
    return {"success": True, "providers": [provider.__dict__ for provider in ai_registry.list_providers()]}


@app.get("/api/ai/routing")
async def ai_routing():
    """Return the active AI routing mode and selected model."""
    routing = ai_registry.get_routing_config()
    return {
        "success": True,
        "routing": routing.__dict__,
        "providers": [provider.__dict__ for provider in ai_registry.list_providers()],
    }


@app.put("/api/ai/routing")
async def update_ai_routing(request: Request):
    """Set automatic routing or explicitly select the preferred provider/model."""
    data = await request.json()
    try:
        provider_id = data.get("active_provider_id")
        routing = ai_registry.set_routing_config(
            mode=data.get("mode", "auto"),
            active_provider_id=int(provider_id) if provider_id is not None else None,
            active_model=data.get("active_model"),
        )
    except (TypeError, ValueError, RuntimeError) as exc:
        return {"success": False, "message": str(exc)}
    return {"success": True, "routing": routing.__dict__}


@app.post("/api/ai/providers")
async def add_ai_provider(request: Request):
    """Create or update an OpenAI-compatible provider and its model pool."""
    data = await request.json()
    try:
        provider_id = ai_registry.upsert_provider(
            name=data.get("name", ""),
            base_url=data.get("base_url", ""),
            api_key=data.get("api_key", ""),
            models=data.get("models"),
            enabled=bool(data.get("enabled", True)),
            timeout=float(data.get("timeout", 45)),
        )
    except (ValueError, RuntimeError) as exc:
        return {"success": False, "message": str(exc)}
    return {"success": True, "provider": ai_registry.public_provider(provider_id)}


@app.delete("/api/ai/providers/{provider_id}")
async def delete_ai_provider(provider_id: int):
    """Delete a configured AI provider and its model pool."""
    return {"success": ai_registry.delete_provider(provider_id)}


@app.post("/api/ai/providers/discover")
async def discover_ai_models(request: Request):
    """Discover models from an OpenAI-compatible provider's /models endpoint."""
    data = await request.json()
    try:
        models = ai_registry.discover_models(
            base_url=data.get("base_url", ""),
            api_key=data.get("api_key", ""),
            timeout=float(data.get("timeout", 15)),
        )
    except (ValueError, RuntimeError) as exc:
        return {"success": False, "message": str(exc)}
    return {"success": True, "models": models}


@app.post("/api/ai/providers/test")
async def test_ai_provider(request: Request):
    """Test a provider/model without persisting its credentials."""
    data = await request.json()
    try:
        from ai.providers import OpenAICompatibleProvider, ProviderConfig

        provider = OpenAICompatibleProvider(
            ProviderConfig(
                name=data.get("name", "test-provider"),
                base_url=data.get("base_url", ""),
                api_key=data.get("api_key", ""),
                model=data.get("model", ""),
                timeout=float(data.get("timeout", 15)),
            )
        )
        response = await provider.generate(
            system="You are a connectivity test. Reply with exactly OK.",
            user="Connectivity test.",
            temperature=0,
            max_tokens=10,
        )
    except Exception as exc:
        logger.warning("AI provider test failed: %s", exc)
        return {"success": False, "message": str(exc)}
    return {"success": True, "provider": response.provider, "model": response.model, "response": response.text}


@app.post("/enrich")
async def enrich_lead(request: Request):
    """Accept a list of URLs for the bot to process."""
    data = await request.json()
    links = data.get("links", [])

    if not links:
        return {"success": False, "message": "No links provided."}

    added_count = 0
    for link in links:
        if link.startswith("http"):
            db.add_lead(source_url=link)
            added_count += 1

    return {"success": True, "message": f"Added {added_count} links to the bot queue!"}


@app.post("/manual-html")
async def manual_html(request: Request):
    """Accept raw HTML and process it through the automatic HTML pipeline."""
    data = await request.json()
    url = data.get("url", "").strip()
    html = data.get("html", "")

    if not url:
        return {"success": False, "message": "Website URL is required."}
    if not html.strip():
        return {"success": False, "message": "HTML source is required."}

    logger.info("Received manual HTML for: %s", url)

    try:
        processor = WebsiteProcessor(page=None)
        cleaned_data = processor.process_html(html)
    except ValueError as exc:
        return {"success": False, "message": str(exc)}
    except Exception:
        logger.exception("Manual HTML processing failed for %s", url)
        return {"success": False, "message": "Unable to process the supplied HTML."}

    emails = cleaned_data["emails"]
    phones = cleaned_data["phones"]
    emails_str = ", ".join(emails)
    phones_str = ", ".join(phones)
    status = "MISSING_DATA" if not emails and not phones else "COMPLETED"
    existing_lead = db.get_lead_by_website(url)

    if existing_lead:
        lead_id = existing_lead["id"]
        db.update_lead_scraped_data(lead_id, emails_str, phones_str, cleaned_data["text"])
        db.update_lead_status(lead_id, status, website=url)
        sheets_manager.update_lead(lead_id=lead_id, company_name=existing_lead["company_name"] or "Unknown", source_url=existing_lead["source_url"] or "Manual HTML", website=url, emails=emails_str, phones=phones_str, status=status)
        message = f"Updated existing Lead ID {lead_id}! Status: {status}"
    else:
        lead_id = db.add_lead(source_url="Manual HTML", company_name="Unknown", location="")
        db.update_lead_status(lead_id, "PROCESSING", website=url)
        db.update_lead_scraped_data(lead_id, emails_str, phones_str, cleaned_data["text"])
        db.update_lead_status(lead_id, status, website=url)
        sheets_manager.add_lead(lead_id=lead_id, company_name="Unknown", source_url="Manual HTML", website=url, emails=emails_str, phones=phones_str, status=status)
        message = f"Created new Lead ID {lead_id}! Status: {status}"

    logger.info(message)
    return {"success": True, "message": message, "lead_id": lead_id, "status": status, "extracted": {"emails": emails, "phones": phones, "text_length": len(cleaned_data["text"])}}


@app.post("/debug/process-html")
async def debug_process_html(request: Request):
    """Development endpoint for parser debugging."""
    data = await request.json()
    html = data.get("html", "")
    if not html.strip():
        return {"success": False, "message": "HTML is required."}

    processor = WebsiteProcessor(page=None)
    result = processor.process_html(html)
    return {"success": True, "text_length": len(result["text"]), "emails": result["emails"], "phones": result["phones"], "text_preview": result["text"][:1000]}
