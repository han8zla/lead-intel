import json

from core.intelligence_store import IntelligenceStore


def test_analysis_run_and_audit_event_are_persisted(tmp_path):
    db_path = tmp_path / "intelligence.db"
    store = IntelligenceStore(str(db_path))
    store.setup_tables()

    run_id = store.start_run(lead_id=42, source_url="https://example.com")
    event_id = store.record_event(
        run_id,
        42,
        "crawl.page_fetched",
        stage="crawl",
        url="https://example.com/contact/",
        status_code=200,
    )
    page_id = store.record_page(
        run_id,
        "https://example.com/contact/",
        status="SUCCESS",
        method="http",
        content_length=1234,
    )
    signal_id = store.record_signal(
        run_id,
        name="contact_form",
        classification="KNOWN",
        confidence=0.97,
        evidence=[{"page": "/contact/", "text": "Contact us"}],
    )
    opportunity_id = store.record_opportunity(
        run_id,
        {
            "type": "inquiry_conversion",
            "title": "Inquiry-to-Response Workflow",
            "priority": "high",
            "score": 84,
            "confidence": 82,
            "impact": 88,
            "solution_fit": 91,
            "evidence": ["Contact form is visible"],
            "unknowns": ["Downstream routing is not visible"],
            "recommendation": "Investigate inquiry routing.",
        },
    )
    store.finish_run(run_id, "COMPLETED", {"opportunities": 1})

    conn = store._connect()
    try:
        assert event_id > 0
        assert page_id > 0
        assert signal_id > 0
        assert opportunity_id > 0

        run = conn.execute(
            "SELECT status, summary_json FROM analysis_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert run["status"] == "COMPLETED"
        assert json.loads(run["summary_json"])["opportunities"] == 1

        event = conn.execute(
            "SELECT event_name, attributes_json FROM audit_events WHERE id = ?",
            (event_id,),
        ).fetchone()
        assert event["event_name"] == "crawl.page_fetched"
        assert json.loads(event["attributes_json"])["status_code"] == 200

        counts = {
            "pages": conn.execute("SELECT COUNT(*) FROM analysis_pages WHERE run_id = ?", (run_id,)).fetchone()[0],
            "signals": conn.execute("SELECT COUNT(*) FROM intelligence_signals WHERE run_id = ?", (run_id,)).fetchone()[0],
            "opportunities": conn.execute("SELECT COUNT(*) FROM intelligence_opportunities WHERE run_id = ?", (run_id,)).fetchone()[0],
            "events": conn.execute("SELECT COUNT(*) FROM audit_events WHERE run_id = ?", (run_id,)).fetchone()[0],
        }
        assert counts == {"pages": 1, "signals": 1, "opportunities": 1, "events": 1}
    finally:
        conn.close()


def test_unknown_signal_can_be_interpreted_and_validated_without_changing_evidence(tmp_path):
    store = IntelligenceStore(str(tmp_path / "intelligence.db"))
    store.setup_tables()
    run_id = store.start_run(lead_id=7, source_url="https://example.com")

    unknown_id = store.record_unknown(
        run_id,
        fingerprint="abc123",
        page_url="https://example.com/contact/",
        observation={"unknown_workflow": "confirmation"},
        context={"industry": "healthcare"},
    )
    interpretation = {
        "classification": "known_candidate",
        "canonical_name": "appointment_confirmation",
        "confidence": "medium",
        "business_meaning": "A possible appointment confirmation workflow.",
        "evidence_needed": ["Confirm the workflow exists beyond the website."],
        "recommended_action": "promote_after_validation",
    }

    assert store.update_unknown(unknown_id, interpretation=interpretation)
    unknown = store.get_unknown(unknown_id)
    assert unknown["interpretation"]["canonical_name"] == "appointment_confirmation"
    assert unknown["validation_status"] == "PENDING"

    assert store.update_unknown(unknown_id, validation_status="VALIDATED")
    validated = store.get_unknown(unknown_id)
    assert validated["validation_status"] == "VALIDATED"
    assert validated["observation"]["unknown_workflow"] == "confirmation"


def test_unknown_validation_rejects_invalid_status(tmp_path):
    store = IntelligenceStore(str(tmp_path / "intelligence.db"))
    store.setup_tables()
    run_id = store.start_run(lead_id=7, source_url="https://example.com")
    unknown_id = store.record_unknown(
        run_id,
        fingerprint="xyz789",
        page_url=None,
        observation={"unknown_workflow": "follow_up"},
        context={},
    )

    try:
        store.update_unknown(unknown_id, validation_status="PROMOTED")
        assert False, "Expected invalid validation status to raise ValueError"
    except ValueError as exc:
        assert "Invalid unknown signal validation status" in str(exc)
