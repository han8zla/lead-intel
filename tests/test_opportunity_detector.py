from processors.opportunity_detector import OpportunityDetector


def test_contact_form_creates_followup_not_lead_capture_gap():
    result = OpportunityDetector().detect(
        signals={
            "contact_page": True,
            "booking": False,
            "lead_form": True,
            "phone": True,
            "email": True,
            "services": True,
            "social": False,
            "ecommerce": False,
            "reviews": False,
            "newsletter": False,
            "live_chat": False,
            "review_cta": False,
        },
        text="Name Email Phone Message Submit",
        pages=["https://example.com/contact/"],
        industry="healthcare",
    )
    types = {item["type"] for item in result}
    assert "inquiry_follow_up" in types
    assert "lead_capture" not in types


def test_booking_and_form_are_distinct_opportunities():
    result = OpportunityDetector().detect(
        signals={
            "contact_page": True,
            "booking": True,
            "lead_form": True,
            "phone": True,
            "email": True,
            "services": True,
            "social": False,
            "ecommerce": False,
            "reviews": True,
            "newsletter": False,
            "live_chat": False,
            "review_cta": False,
        },
        text="book appointment Name Email Phone Message Submit reviews",
        pages=["https://example.com/", "https://example.com/contact/"],
        industry="healthcare",
    )
    types = {item["type"] for item in result}
    assert "appointment_follow_up" in types
    assert "inquiry_follow_up" in types


def test_missing_conversion_path_is_actionable():
    result = OpportunityDetector().detect(
        signals={
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
        },
        text="our services contact us phone email",
        pages=["https://example.com/contact/"],
        industry="professional_services",
    )
    types = {item["type"] for item in result}
    assert "lead_capture" in types
