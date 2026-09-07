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
                opportunity_score INTEGER,
                opportunity_data TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        self._ensure_column(cursor, "leads", "opportunity_score", "INTEGER")
        self._ensure_column(cursor, "leads", "opportunity_data", "TEXT")

        conn.commit()
        conn.close()
        logger.info("Database tables ready.")

    @staticmethod
    def _ensure_column(cursor, table: str, column: str, column_type: str) -> None:
        """Add a column to an existing installation without destroying data."""
        cursor.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cursor.fetchall()}
        if column not in existing:
            cursor.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"
            )
            logger.info("Added database column: %s.%s", table, column)

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
        logger.info("Added lead to queue: %s (ID: %s)", source_url, lead_id)
        return lead_id

    def get_next_pending(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM leads WHERE status = 'PENDING' ORDER BY id ASC LIMIT 1"
        )
        lead = cursor.fetchone()
        conn.close()
        return lead

    def update_lead_status(
        self,
        lead_id: int,
        status: str,
        website: str = None,
        company_name: str = None,
    ):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE leads
            SET status = ?,
                website = COALESCE(?, website),
                company_name = COALESCE(?, company_name),
                updated_at = datetime('now')
            WHERE id = ?
        """, (status, website, company_name, lead_id))
        conn.commit()
        conn.close()
        logger.info("Updated Lead ID %s to status: %s", lead_id, status)

    def update_lead_scraped_data(
        self,
        lead_id: int,
        emails: str,
        phones: str,
        text: str,
    ):
        """Save scraped text and contacts to the database."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE leads
            SET extracted_emails = ?,
                extracted_phones = ?,
                body_text = ?,
                updated_at = datetime('now')
            WHERE id = ?
        """, (emails, phones, text, lead_id))
        conn.commit()
        conn.close()
        logger.info("Saved scraped data for Lead ID %s", lead_id)

    def update_lead_analysis(
        self,
        lead_id: int,
        opportunity_score: int,
        opportunity_data: str,
    ):
        """Save deterministic website opportunity analysis."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE leads
            SET opportunity_score = ?,
                opportunity_data = ?,
                updated_at = datetime('now')
            WHERE id = ?
        """, (opportunity_score, opportunity_data, lead_id))
        conn.commit()
        conn.close()
        logger.info(
            "Saved opportunity analysis for Lead ID %s: score=%s",
            lead_id,
            opportunity_score,
        )

    def get_lead_by_website(self, website_url: str):
        """Find a lead by website URL."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM leads WHERE website = ? ORDER BY id DESC LIMIT 1",
            (website_url,),
        )
        lead = cursor.fetchone()
        conn.close()
        return lead

    def get_dashboard_leads(self, limit: int = 100):
        """Return recent leads with their stored analysis for the dashboard."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, company_name, location, source_url, website, status,
                   extracted_emails, extracted_phones, opportunity_score,
                   opportunity_data, created_at, updated_at
            FROM leads
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, min(limit, 500)),),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_dashboard_stats(self):
        """Return high-level counts used by the dashboard cards."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM leads")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'PENDING'")
        pending = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'PROCESSING'")
        processing = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'COMPLETED'")
        completed = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'FAILED'")
        failed = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM leads WHERE opportunity_score >= 7")
        high_opportunity = cursor.fetchone()[0]

        cursor.execute("SELECT AVG(opportunity_score) FROM leads WHERE opportunity_score IS NOT NULL")
        average_score = cursor.fetchone()[0]

        conn.close()

        return {
            "total": total,
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "failed": failed,
            "high_opportunity": high_opportunity,
            "average_score": round(average_score, 1) if average_score is not None else None,
        }


if __name__ == "__main__":
    db = Database()
    db.setup_tables()
    print("Database created successfully!")
