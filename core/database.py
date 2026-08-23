import sqlite3
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)

class Database:
    def __init__(self, db_path: str = "./data/lead_intelligence.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def setup_tables(self):
        logger.info("Setting up database tables...")
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT,
                location TEXT,
                source_url TEXT NOT NULL,
                website TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                extracted_emails TEXT,
                extracted_phones TEXT,
                body_text TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        conn.close()
        logger.info("Database tables ready.")

    def add_lead(self, source_url: str, company_name: str = "", location: str = ""):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO leads (company_name, location, source_url) 
            VALUES (?, ?, ?)
        """, (company_name, location, source_url))
        conn.commit()
        lead_id = cursor.lastrowid
        conn.close()
        logger.info(f"Added lead to queue: {source_url} (ID: {lead_id})")
        return lead_id

    def get_next_pending(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE status = 'PENDING' ORDER BY id ASC LIMIT 1")
        lead = cursor.fetchone()
        conn.close()
        return lead

    def update_lead_status(self, lead_id: int, status: str, website: str = None, company_name: str = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE leads 
            SET status = ?, website = ?, company_name = COALESCE(?, company_name), updated_at = datetime('now') 
            WHERE id = ?
        """, (status, website, company_name, lead_id))
        conn.commit()
        conn.close()
        logger.info(f"Updated Lead ID {lead_id} to status: {status}")

    def update_lead_scraped_data(self, lead_id: int, emails: str, phones: str, text: str):
        """Saves the scraped text and contacts to the database."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE leads 
            SET extracted_emails = ?, extracted_phones = ?, body_text = ?, updated_at = datetime('now') 
            WHERE id = ?
        """, (emails, phones, text, lead_id))
        conn.commit()
        conn.close()
        logger.info(f"Saved scraped data for Lead ID {lead_id}")
    
    def get_lead_by_website(self, website_url: str):
        """Finds a lead by its website URL so we can update it instead of duplicating."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE website = ? ORDER BY id DESC LIMIT 1", (website_url,))
        lead = cursor.fetchone()
        conn.close()
        return lead

if __name__ == "__main__":
    db = Database()
    db.setup_tables()
    print("Database created successfully!")