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
    """Accepts raw HTML pasted by the user, processes it instantly, deduplicates"""
    data = await request.json()
    url = data.get("url", "")
    html = data.get("html", "")

    if not url or not html:
        return {"success": False, "message": "URL and HTML are required."}

    logger.info(f"Received manual HTML for: {url}")
    
    # Use our existing processor logic to clean the HTML
    processor = WebsiteProcessor(page=None)
    cleaned_data = processor._extract_data_from_html(html)
    emails_str = ", ".join(cleaned_data["emails"])
    phones_str = ", ".join(cleaned_data["phones"])
    
    # Determine Status: If no email AND no phone, it's missing data!
    if len(cleaned_data["emails"]) == 0 and len(cleaned_data["phones"]) == 0:
        status = "MISSING_DATA"
    else:
        status = "COMPLETED"

    # CHECK FOR DUPLICATES: Does this website already exist in our database?
    existing_lead = db.get_lead_by_website(url)
    
    if existing_lead:
        # UPDATE EXISTING LEAD
        lead_id = existing_lead['id']
        logger.info(f"Found existing Lead ID {lead_id} for {url}. Updating with manual data.")
        db.update_lead_scraped_data(lead_id, emails=emails_str, phones=phones_str, text=cleaned_data["text"])
        db.update_lead_status(lead_id, status, website=url)
        
        # Update Google Sheet (we will build this function next)
        sheets_manager.update_lead(
            lead_id=lead_id,
            company_name=existing_lead['company_name'] or "Unknown",
            source_url=existing_lead['source_url'] or "Manual Paste",
            website=url,
            emails=emails_str,
            phones=phones_str,
            status=status
        )
        msg = f"Updated existing Lead ID {lead_id}! Status: {status}"
    else:
        # CREATE NEW LEAD
        lead_id = db.add_lead(source_url="Manual Paste", company_name="Unknown", location="")
        db.update_lead_status(lead_id, "PROCESSING", website=url)
        db.update_lead_scraped_data(lead_id, emails=emails_str, phones=phones_str, text=cleaned_data["text"])
        db.update_lead_status(lead_id, status, website=url)
        
        # Push to Google Sheet
        sheets_manager.add_lead(
            lead_id=lead_id,
            company_name="Unknown",
            source_url="Manual Paste",
            website=url,
            emails=emails_str,
            phones=phones_str,
            status=status
        )
        msg = f"Created new Lead ID {lead_id}! Status: {status}"

    logger.info(msg)
    return {"success": True, "message": msg}