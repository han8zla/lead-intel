from core.unknown_signal_registry import UnknownSignalRegistry


def test_unknown_signal_can_be_promoted_and_reused(tmp_path):
    registry = UnknownSignalRegistry(str(tmp_path / "intelligence.db"))

    signal_id = registry.promote(
        fingerprint="assessment-widget",
        name="Patient Assessment Widget",
        pattern={"text": "start assessment", "audience": "patients"},
        description="Interactive assessment entry point detected on a website.",
        validation_source="human_review",
    )

    assert signal_id > 0
    assert registry.record_occurrence("assessment-widget") is True

    signals = registry.list_signals()
    assert len(signals) == 1
    assert signals[0]["name"] == "Patient Assessment Widget"
    assert signals[0]["classification"] == "KNOWN"
    assert signals[0]["occurrence_count"] == 1
    assert signals[0]["pattern"]["audience"] == "patients"


def test_promoting_same_fingerprint_updates_existing_signal(tmp_path):
    registry = UnknownSignalRegistry(str(tmp_path / "intelligence.db"))

    first_id = registry.promote(
        fingerprint="widget-123",
        name="Assessment Widget",
        pattern={"version": 1},
    )
    second_id = registry.promote(
        fingerprint="widget-123",
        name="Patient Assessment Widget",
        pattern={"version": 2, "audience": "patients"},
        validation_source="human_review",
    )

    assert second_id == first_id
    signal = registry.get_by_fingerprint("widget-123")
    assert signal["name"] == "Patient Assessment Widget"
    assert signal["pattern"]["version"] == 2
