from processors.business_analyzer import BusinessAnalyzer
from processors.opportunity_detector import OpportunityDetector


def test_opportunity_score_uses_impact_confidence_and_solution_fit():
    detector = OpportunityDetector()
    opportunities = detector.detect(
        signals={"booking": True, "email": True, "phone": True},
        pages=["https://example.com/appointments"],
        industry="healthcare",
    )

    assert opportunities[0]["score"] == 88
    assert opportunities[0]["impact"] == 90
    assert opportunities[0]["confidence"] == 82
    assert opportunities[0]["solution_fit"] == 92


def test_overall_score_has_band_and_explainable_breakdown():
    detector = OpportunityDetector()
    opportunities = [
        {"type": "appointment_lifecycle", "score": 94},
        {"type": "reputation_follow_up", "score": 86},
        {"type": "conversion_path", "score": 68},
    ]

    result = detector.overall_score(opportunities)

    assert result["score"] == 92
    assert result["band"] == "high"
    assert result["breakdown"]["top_opportunity"] == 94
    assert result["breakdown"]["secondary_opportunity"] == 86
    assert result["breakdown"]["top_type"] == "appointment_lifecycle"
    assert "tertiary_opportunity" not in result["breakdown"]


def test_generic_products_text_does_not_create_ecommerce_opportunity():
    analyzer = BusinessAnalyzer()
    result = analyzer.analyze(
        "https://example.com",
        html="<html><title>Dental Clinic</title><body>Our products include whitening products. Contact us for appointments.</body></html>",
        text="Dental clinic. Our products include whitening products. Contact us for appointments.",
        scraped_data={"pages": [], "page_details": []},
    )

    assert result["signals"]["ecommerce"] is False
    assert not any(item["type"] == "commerce_lifecycle" for item in result["opportunities"])


def test_explicit_transaction_signal_creates_ecommerce_opportunity():
    analyzer = BusinessAnalyzer()
    result = analyzer.analyze(
        "https://example.com",
        html="<html><title>Online Store</title><body>Buy now and add to cart. Checkout securely.</body></html>",
        text="Online store. Buy now and add to cart. Checkout securely.",
        scraped_data={"pages": [], "page_details": []},
    )

    assert result["signals"]["ecommerce"] is True
    assert any(item["type"] == "commerce_lifecycle" for item in result["opportunities"])
