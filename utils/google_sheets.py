import gspread
from google.oauth2.service_account import Credentials
from utils.logger import get_logger

logger = get_logger(__name__)

# The scopes define what permissions our bot has
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.metadata.readonly"
]

class GoogleSheetsManager:
    def __init__(self, credentials_path: str = "credentials.json", sheet_name: str = "Lead Intelligence"):
        self.sheet = None
        try:
            # Load the credentials
            creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
            
            # Authorize with Google
            client = gspread.authorize(creds)
            
            # Open the specific spreadsheet
            self.sheet = client.open(sheet_name).sheet1
            logger.info(f"Successfully connected to Google Sheet: {sheet_name}")
        except Exception as e:
            logger.error(f"Failed to connect to Google Sheets: {e}")
            logger.error("Make sure you shared the sheet with the service account email!")

    def add_lead(self, lead_id: int, company_name: str, source_url: str, website: str, emails, phones, status: str, text: str = ""):
        """Appends a new row to the Google Sheet."""
        if not self.sheet:
            logger.warning("Google Sheet not connected. Skipping sheet update.")
            return

        try:
            # Truncate text to 500 characters so it doesn't break the Google Sheet layout
            text_preview = (text or "")[:500] + "..." if len(text or "") > 500 else text or ""
            
            row_data = [
            lead_id,
            company_name or "Unknown",
            source_url or "",
            website or "",
            ", ".join(emails) if isinstance(emails, list) else (emails or ""),
            ", ".join(phones) if isinstance(phones, list) else (phones or ""),
            status or "",
            text_preview
            ]
            
            self.sheet.append_row(row_data)
            logger.info(f"Pushed Lead ID {lead_id} to Google Sheets.")
        except Exception as e:
            logger.error(f"Failed to push lead to Google Sheets: {e}")

    def update_lead(self,
    lead_id: int,
    company_name: str, source_url: str, website: str, emails, phones, status: str):
        """Finds an existing row by ID and updates it."""
        if not self.sheet:
            return
        try:
            # Find the row with the matching ID in Column A
            cell = self.sheet.find(str(lead_id), in_column=1)
            if cell:
                row_number = cell.row
                # Update the cells in that row
                self.sheet.update(f"B{row_number}:G{row_number}", [[
                    company_name or "Unknown", 
                    source_url or "", 
                    website or "", 
                    emails or "", 
                    phones or "", 
                    status or ""
                ]])
                logger.info(f"Updated Lead ID {lead_id} in Google Sheets (Row {row_number}).")
            else:
                # Fallback: if ID not found, just append it
                self.add_lead(lead_id, company_name, source_url, website, emails, phones, status)
        except Exception as e:
            logger.error(f"Failed to update lead in Google Sheets: {e}")