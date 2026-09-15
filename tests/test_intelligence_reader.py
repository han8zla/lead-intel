from core.intelligence_reader import IntelligenceReader
from core.intelligence_store import IntelligenceStore


def test_reader_returns_run_timeline_and_structured_records(tmp_path):
    db_path = tmp_path / "intelligence.db"
    store = IntelligenceStore(str(db_path))
    store.setup_tables()

    run_id = store.start_run(lead_id=7, source_url="https://example.com")
    store.record_event(
        run_id,
        7,
        "crawl.page_fetched",
        stage="crawl",
        url="https://example.com/contact/",
        status_code=200,
    )
    store.record_observation(
        run_id,
        page_url="https://example.com/contact/",
        kind="dom",
        key="form_count",
        value=1,
        evidence={"selector": "form"},
        confidence=1.0,
    )
    store.record_signal(
        run_id,
        name="lead_form",
        classification="KNOWN",
        confidence=0.95,
        evidence=[{"page": "/contact/"}],
    )
    store.record_unknown(
        run_id,
        fingerprint="assessment-widget",
        page_url="https://example.com/contact/",
        observation={"text": "Start assessment"},
        context={"nearby": "new patients"},
    )
    store.record_ai(
        run_id,
        purpose="business_analysis",
        provider="test",
        model="test-model",
        input_hash="abc",
        status="COMPLETED",
        input_summary={"signals": 1},
        output={"industry": "healthcare"},
    )
    store.record_opportunity(
        run_id,
        {
            "type": "inquiry_conversion",
            "title": "Inquiry-to-Response Workflow",
            "priority": "high",
            "score": 84,
            "confidence": 80,
            "impact": 90,
            "solution_fit": 85,
            "evidence": ["Lead form visible"],
            "unknowns": ["Routing not visible"],
            "recommendation": "Investigate routing.",
        },
    )
    store.finish_run(run_id, "COMPLETED", {"opportunities": 1})

    reader = IntelligenceReader(str(db_path))

    run = reader.get_run(run_id)
    assert run["status"] == "COMPLETED"
    assert run["summary"]["opportunities"] == 1

    assert len(reader.get_run_timeline(run_id)) == 1
    assert reader.get_run_timeline(run_id)[0]["attributes"]["status_code"] == 200
    assert len(reader.get_run_observations(run_id)) == 1
    assert reader.get_run_observations(run_id)[0]["value"] == 1
    assert len(reader.get_run_signals(run_id)) == 1
    assert len(reader.get_run_unknowns(run_id, validation_status="PENDING")) == 1
    assert len(reader.get_run_ai(run_id)) == 1
    assert reader.get_run_ai(run_id)[0]["output"]["industry"] == "healthcare"
    assert reader.get_run_opportunities(run_id)[0]["score"] == 84


def test_reader_lists_runs_and_reports_health(tmp_path):
    db_path = tmp_path / "intelligence.db"
    store = IntelligenceStore(str(db_path))
    store.setup_tables()

    completed = store.start_run(lead_id=1, source_url="https://one.example")
    store.finish_run(completed, "COMPLETED")

    failed = store.start_run(lead_id=2, source_url="https://two.example")
    store.fail_run(failed, "HTTPError", "request failed")

    reader = IntelligenceReader(str(db_path))
    runs = reader.list_runs()
    health = reader.get_system_health()

    assert len(runs) == 2
    assert health == {
        "total_runs": 2,
        "completed_runs": 1,
        "failed_runs": 1,
        "running_runs": 0,
        "failure_rate": 0.5,
    }
