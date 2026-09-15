from processors.html_processor import HTMLProcessor


def test_deep_dom_extraction_preserves_business_and_technical_context():
    html = """
    <html lang="en">
      <head>
        <title>Example Health</title>
        <meta name="description" content="Primary care and patient services">
        <link rel="canonical" href="https://example.org/">
        <script type="application/ld+json">
          {"@context":"https://schema.org","@type":"MedicalBusiness","name":"Example Health"}
        </script>
        <script src="https://assets.calendly.com/widget.js"></script>
      </head>
      <body>
        <h1>Primary Care</h1>
        <h2>New Patients</h2>
        <a href="/appointments/" aria-label="Schedule your appointment">Book Appointment</a>
        <a href="https://calendly.com/example">Schedule online</a>
        <a href="/portal/">Patient Portal</a>
        <a href="/billing/">Pay Your Bill</a>
        <button data-testid="start-assessment" aria-label="Start your assessment">Start</button>
        <form action="/intake" method="post" aria-label="Patient Intake">
          <input name="first_name" type="text" autocomplete="given-name">
          <input name="insurance" type="text">
          <input name="referral_source" type="text">
          <button type="submit">Submit</button>
        </form>
      </body>
    </html>
    """

    result = HTMLProcessor().process(html)
    dom = result["dom"]

    assert dom["metadata"]["title"] == "Example Health"
    assert "Primary Care" in dom["headings"]["h1"]
    assert any(link["type"] == "booking" for link in dom["links"])
    assert any(link["type"] == "portal" for link in dom["links"])
    assert any(link["type"] == "payment" for link in dom["links"])
    assert dom["forms"][0]["method"] == "post"
    field_names = {field["name"] for field in dom["forms"][0]["fields"]}
    assert {"first_name", "insurance", "referral_source"}.issubset(field_names)
    assert "calendly" in dom["technologies"]
    assert dom["json_ld"][0]["@type"] == "MedicalBusiness"
    assert any(item["attributes"].get("data-testid") == "start-assessment" for item in dom["attribute_samples"])
