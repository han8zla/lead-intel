from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from core.database import Database
from crawlers.website_processor import WebsiteProcessor
from utils.logger import get_logger
from utils.google_sheets import GoogleSheetsManager


logger = get_logger(__name__)


app = FastAPI()
templates = Jinja2Templates(directory="templates")
db = Database()
sheets_manager = GoogleSheetsManager()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})

@app.post("/enrich")
async def enrich_lead(request: Request):
    """Accepts a list of URLs for the bot to process"""
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
    """
    Accept raw HTML supplied by the user and process it
    through the same HTML pipeline used by automatic scraping.
    """

    data = await request.json()

    url = data.get("url", "").strip()
    html = data.get("html", "")

    if not url:
        return {
            "success": False,
            "message": "Website URL is required.",
        }

    if not html.strip():
        return {
            "success": False,
            "message": "HTML source is required.",
        }

    logger.info(
        "Received manual HTML for: %s",
        url,
    )

    try:
        processor = WebsiteProcessor(page=None)
        cleaned_data = processor.process_html(html)

    except ValueError as exc:
        return {
            "success": False,
            "message": str(exc),
        }

    except Exception as exc:
        logger.exception(
            "Manual HTML processing failed for %s",
            url,
        )

        return {
            "success": False,
            "message": "Unable to process the supplied HTML.",
        }

    emails = cleaned_data["emails"]
    phones = cleaned_data["phones"]

    emails_str = ", ".join(emails)
    phones_str = ", ".join(phones)

    if not emails and not phones:
        status = "MISSING_DATA"
    else:
        status = "COMPLETED"

    existing_lead = db.get_lead_by_website(url)

    if existing_lead:
        lead_id = existing_lead["id"]

        logger.info(
            "Updating existing Lead ID %s",
            lead_id,
        )

        db.update_lead_scraped_data(
            lead_id,
            emails=emails_str,
            phones=phones_str,
            text=cleaned_data["text"],
        )

        db.update_lead_status(
            lead_id,
            status,
            website=url,
        )

        sheets_manager.update_lead(
            lead_id=lead_id,
            company_name=(
                existing_lead["company_name"]
                or "Unknown"
            ),
            source_url=(
                existing_lead["source_url"]
                or "Manual HTML"
            ),
            website=url,
            emails=emails_str,
            phones=phones_str,
            status=status,
        )

        message = (
            f"Updated existing Lead ID "
            f"{lead_id}! Status: {status}"
        )

    else:
        lead_id = db.add_lead(
            source_url="Manual HTML",
            company_name="Unknown",
            location="",
        )

        db.update_lead_status(
            lead_id,
            "PROCESSING",
            website=url,
        )

        db.update_lead_scraped_data(
            lead_id,
            emails=emails_str,
            phones=phones_str,
            text=cleaned_data["text"],
        )

        db.update_lead_status(
            lead_id,
            status,
            website=url,
        )

        sheets_manager.add_lead(
            lead_id=lead_id,
            company_name="Unknown",
            source_url="Manual HTML",
            website=url,
            emails=emails_str,
            phones=phones_str,
            status=status,
        )

        message = (
            f"Created new Lead ID "
            f"{lead_id}! Status: {status}"
        )

    logger.info(message)

    return {
        "success": True,
        "message": message,
        "lead_id": lead_id,
        "status": status,
        "extracted": {
            "emails": emails,
            "phones": phones,
            "text_length": len(cleaned_data["text"]),
        },
    }

@app.post("/debug/process-html")
async def debug_process_html(request: Request):
    """
    Development endpoint.

    Processes HTML without touching the database.
    Useful while developing the parser.
    """

    data = await request.json()

    html = data.get("html", "")

    if not html.strip():
        return {
            "success": False,
            "message": "HTML is required.",
        }

    processor = WebsiteProcessor(page=None)

    result = processor.process_html(html)

    return {
        "success": True,
        "text_length": len(result["text"]),
        "emails": result["emails"],
        "phones": result["phones"],
        "text_preview": result["text"][:1000],
    }