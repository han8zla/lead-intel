from processors.opportunity_detector import OpportunityDetector


BASE_SIGNALS = {
    "contact_page": True,
    "booking": False,
    "lead_form": False,
    "phone": True,
    "email": True,
    "services": True,
    "social": False,
    "ecommerce": False,
    "reviews": False,
    "newsletter": False,
    "live_chat": False,
    "review_cta": False,
}


def test_contact_form_creates_inquiry_workflow_not_generic_lead_capture():
    signals = {**BASE_SIGNALS, "lead_form": True}
    result = OpportunityDetector().detect(
        signals=signals,
        text="Name Email Phone Message Submit contact form",
        pages=["https://example.com/contact/"],
        industry="healthcare",
    )
    types = {item["type"] for item in result}
    assert "inquiry_conversion" in types
    assert "conversion_path" not in types
    opportunity = next(item for item in result if item["type"] == "inquiry_conversion")
    assert opportunity["unknowns"]
    assert opportunity["confidence"] < 100


def test_booking_is_a_lifecycle_opportunity_not_proof_that_follow_up_is_missing():
    signals = {**BASE_SIGNALS, "booking": True}
    result = OpportunityDetector().detect(
        signals=signals,
        text="book appointment schedule online healthcare patient",
        pages=["https://example.com/appointments/"],
        industry="healthcare",
    )
    opportunity = next(item for item in result if item["type"] == "appointment_lifecycle")
    assert opportunity["title"] == "Appointment Lifecycle Automation"
    assert "Existing reminder/confirmation automation is not visible from the website" in opportunity["unknowns"]
    assert opportunity["confidence"] < 100


def test_multiple_audiences_create_routing_opportunity():
    result = OpportunityDetector().detect(
        signals=BASE_SIGNALS,
        text="families caregivers professionals referrals home care services",
        pages=["https://example.com/", "https://example.com/contact/"],
        industry="healthcare",
    )
    opportunity = next(item for item in result if item["type"] == "audience_routing")
    evidence = opportunity["evidence"][0]
    assert "families" in evidence
    assert "referrers" in evidence
    assert "professionals" in evidence
    assert opportunity["solution_fit"] >= 90


def test_intake_and_referral_are_separate_from_marketing_inquiry():
    result = OpportunityDetector().detect(
        signals=BASE_SIGNALS,
        text="patient intake forms referral referrals enrollment care coordination",
        pages=["https://example.com/referrals/"],
        industry="healthcare",
    )
    types = {item["type"] for item in result}
    assert "intake_coordination" in types
    opportunity = next(item for item in result if item["type"] == "intake_coordination")
    assert opportunity["impact"] >= 90


def test_ecommerce_is_not_created_from_generic_products_language():
    signals = {**BASE_SIGNALS, "ecommerce": False}
    result = OpportunityDetector().detect(
        signals=signals,
        text="products services treatments patient information",
        pages=["https://example.com/"],
        industry="healthcare",
    )
    types = {item["type"] for item in result}
    assert "commerce_lifecycle" not in types


def test_explicit_ecommerce_creates_conservative_commerce_opportunity():
    signals = {**BASE_SIGNALS, "ecommerce": True}
    result = OpportunityDetector().detect(
        signals=signals,
        text="shop now add to cart checkout products",
        pages=["https://example.com/shop/"],
        industry="ecommerce",
    )
    opportunity = next(item for item in result if item["type"] == "commerce_lifecycle")
    assert opportunity["confidence"] < 100


def test_overall_score_is_priority_not_probability():
    detector = OpportunityDetector()
    result = detector.overall_score([
        {
            "type": "appointment_lifecycle",
            "score": 90,
        },
        {
            "type": "reputation_follow_up",
            "score": 60,
        },
    ])
    assert result["score"] == 82
    assert "not a probability of purchase" in result["breakdown"]["reason"]
