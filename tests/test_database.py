import json

from core.database import Database


def test_dashboard_stats_and_leads(tmp_path):
    db = Database(str(tmp_path / "lead-intelligence.db"))
    db.setup_tables()

    high_id = db.add_lead("https://example.com", company_name="Example Co")
    low_id = db.add_lead("https://example.org", company_name="Example Org")

    db.update_lead_status(high_id, "COMPLETED", website="https://example.com")
    db.update_lead_status(low_id, "PENDING", website="https://example.org")
    db.update_lead_analysis(
        high_id,
        9,
        json.dumps({"opportunities": [{"type": "lead_capture", "score": 9}]}),
    )
    db.update_lead_analysis(low_id, 4, json.dumps({"opportunities": []}))

    stats = db.get_dashboard_stats()
    assert stats["total"] == 2
    assert stats["completed"] == 1
    assert stats["pending"] == 1
    assert stats["high_opportunity"] == 1
    assert stats["average_score"] == 6.5

    leads = db.get_dashboard_leads()
    assert [lead["id"] for lead in leads] == [low_id, high_id]
    assert leads[0]["opportunity_score"] == 4
    assert leads[1]["opportunity_score"] == 9
