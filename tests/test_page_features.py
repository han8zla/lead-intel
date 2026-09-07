from processors.business_analyzer import BusinessAnalyzer
from processors.html_processor import HTMLProcessor


def test_html_processor_detects_real_contact_form():
    html = """
    <html><head><title>Example Clinic</title></head><body>
      <h1>Contact Us</h1>
      <form action="/contact-submit">
        <input name="full_name" placeholder="Your name">
        <input name="email" placeholder="Email address">
        <input name="phone" placeholder="Phone number">
        <textarea name="message">Message</textarea>
        <button type="submit">Send Message</button>
      </form>
    </body></html>
    """
    data = HTMLProcessor().process(html)
    assert data["features"]["form_count"] == 1
    assert data["features"]["lead_form"] is True
    assert data["features"]["form_details"][0]["action"] == "/contact-submit"


def test_analyzer_uses_page_level_form_evidence():
    analysis = BusinessAnalyzer().analyze(
        "https://example.com",
        text="Example Clinic Contact Us services physician",
        scraped_data={
            "text": "Example Clinic Contact Us services physician",
            "emails": ["info@example.org"],
            "phones": ["310-555-1212"],
            "pages": ["https://example.com", "https://example.com/contact/"],
            "page_details": [{
                "url": "https://example.com/contact/",
                "features": {"lead_form": True, "form_count": 1},
            }],
        },
    )
    assert analysis["signals"]["lead_form"] is True
    assert any("https://example.com/contact/" in item for item in analysis["signal_evidence"]["lead_form"])
    assert not any(item["type"] == "lead_capture" for item in analysis["opportunities"])
    assert any(item["type"] == "inquiry_follow_up" for item in analysis["opportunities"])
