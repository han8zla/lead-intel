from processors.business_analyzer import BusinessAnalyzer
from processors.opportunity_detector import OpportunityDetector


def test_opportunity_score_blends_impact_and_confidence():
    detector = OpportunityDetector()
    opportunities = detector.detect(
        signals={"booking": True, "email": True, "phone": True},
        pages=["https://example.com/appointments"],
        industry="healthcare",
    )

    assert opportunities[0]["score"] == 94
    assert opportunities[0]["impact"] == 95
    assert opportunities[0]["confidence"] == 92


def test_overall_score_has_band_and_explainable_breakdown():
    detector = OpportunityDetector()
    opportunities = [
        {"score": 94},
        {"score": 86},
        {"score": 68},
    ]

    result = detector.overall_score(opportunities)

    assert result["score"] == 88
    assert result["band"] == "high"
    assert result["breakdown"]["top_opportunity"] == 94
    assert result["breakdown"]["secondary_opportunity"] == 86
    assert result["breakdown"]["tertiary_opportunity"] == 68


def test_generic_products_text_does_not_create_ecommerce_opportunity():
    analyzer = BusinessAnalyzer()
    result = analyzer.analyze(
        "https://example.com",
        html="<html><title>Dental Clinic</title><body>Our products include whitening products. Contact us for appointments.</body></html>",
        text="Dental clinic. Our products include whitening products. Contact us for appointments.",
        scraped_data={"pages": [], "page_details": []},
    )

    assert result["signals"]["ecommerce"] is False
    assert not any(item["type"] == "ecommerce_automation" for item in result["opportunities"])


def test_explicit_transaction_signal_creates_ecommerce_opportunity():
    analyzer = BusinessAnalyzer()
    result = analyzer.analyze(
        "https://example.com",
        html="<html><title>Online Store</title><body>Buy now and add to cart. Checkout securely.</body></html>",
        text="Online store. Buy now and add to cart. Checkout securely.",
        scraped_data={"pages": [], "page_details": []},
    )

    assert result["signals"]["ecommerce"] is True
    assert any(item["type"] == "ecommerce_automation" for item in result["opportunities"])
