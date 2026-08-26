import gspread
from google.oauth2.service_account import Credentials
from utils.logger import get_logger


logger = get_logger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]


class GoogleSheetsManager:
    def __init__(
        self,
        credentials_path: str = "credentials.json",
        sheet_name: str = "Lead Intelligence",
    ):
        self.sheet = None
        try:
            creds = Credentials.from_service_account_file(
                credentials_path,
                scopes=SCOPES,
            )
            client = gspread.authorize(creds)
            self.sheet = client.open(sheet_name).sheet1
            logger.info("Successfully connected to Google Sheet: %s", sheet_name)
        except Exception as exc:
            logger.error("Failed to connect to Google Sheets: %s", exc)
            logger.error("Make sure you shared the sheet with the service account email!")

    def add_lead(
        self,
        lead_id: int,
        company_name: str,
        source_url: str,
        website: str,
        emails,
        phones,
        status: str,
        text: str = "",
        opportunity_score: int | None = None,
    ):
        """Append a new lead row, including the transparent opportunity score."""
        if not self.sheet:
            logger.warning("Google Sheet not connected. Skipping sheet update.")
            return

        try:
            text_preview = (
                (text or "")[:500] + "..."
                if len(text or "") > 500
                else text or ""
            )

            row_data = [
                lead_id,
                company_name or "Unknown",
                source_url or "",
                website or "",
                self._normalize_value(emails),
                self._normalize_value(phones),
                status or "",
                text_preview,
                opportunity_score if opportunity_score is not None else "",
            ]

            self.sheet.append_row(row_data)
            logger.info("Pushed Lead ID %s to Google Sheets.", lead_id)
        except Exception as exc:
            logger.error("Failed to push lead to Google Sheets: %s", exc)

    def update_lead(
        self,
        lead_id: int,
        company_name: str,
        source_url: str,
        website: str,
        emails,
        phones,
        status: str,
        opportunity_score: int | None = None,
    ):
        """Find an existing row by ID and update it."""
        if not self.sheet:
            return

        try:
            cell = self.sheet.find(str(lead_id), in_column=1)
            if cell:
                row_number = cell.row
                self.sheet.update(
                    f"B{row_number}:I{row_number}",
                    [[
                        company_name or "Unknown",
                        source_url or "",
                        website or "",
                        self._normalize_value(emails),
                        self._normalize_value(phones),
                        status or "",
                        "",
                        opportunity_score if opportunity_score is not None else "",
                    ]],
                )
                logger.info(
                    "Updated Lead ID %s in Google Sheets (Row %s).",
                    lead_id,
                    row_number,
                )
            else:
                self.add_lead(
                    lead_id,
                    company_name,
                    source_url,
                    website,
                    emails,
                    phones,
                    status,
                    opportunity_score=opportunity_score,
                )
        except Exception as exc:
            logger.error("Failed to update lead in Google Sheets: %s", exc)

    @staticmethod
    def _normalize_value(value):
        if isinstance(value, (list, tuple, set)):
            return ", ".join(str(item) for item in value if item)
        return str(value or "")
