# Lead Intelligence Platform

> Website enrichment, business analysis, opportunity scoring, and AI-assisted outreach for qualified leads.

[![CI](https://github.com/han8zla/lead-intel/actions/workflows/ci.yml/badge.svg)](https://github.com/han8zla/lead-intel/actions/workflows/ci.yml)

Lead Intelligence is a Python-based lead research and enrichment platform that turns a website URL into structured business intelligence. It combines website ingestion, contact extraction, business-signal analysis, opportunity detection, persistent lead storage, dashboard reporting, and optional AI-generated outreach drafts.

The project is designed as a modular foundation for sales operations and automation workflows rather than a one-off scraper.

## What it does

```text
Website / Lead URL
       |
       v
HTTP-first ingestion
       |
       +----> Playwright fallback for difficult pages
       |
       v
Contact & content extraction
       |
       v
Business signal analysis
       |
       v
Opportunity detection + scoring
       |
       +----> AI outreach draft (optional)
       |
       v
SQLite persistence
       |
       v
Dashboard / Google Sheets
```

## Key capabilities

- **HTTP-first website ingestion** with Playwright as a fallback for JavaScript-heavy or protected pages.
- **Contact extraction** for business email addresses and phone numbers, including common `mailto:` / `tel:` patterns.
- **Business analysis** for signals such as contact paths, booking, forms, services, reviews, ecommerce, newsletters, live chat, and social presence.
- **Opportunity detection** that converts observed website signals into actionable automation opportunities instead of treating every missing feature as an opportunity.
- **Transparent opportunity scoring** so leads can be prioritized before outreach.
- **AI-assisted personalization** using OpenAI-compatible providers without coupling the application to one vendor.
- **Automatic AI model failover** across configured models when a provider returns retryable rate-limit, server, or network failures.
- **SQLite storage** for leads, extracted data, analysis, and processing state.
- **Web dashboard** for pipeline statistics, opportunity scores, contacts, and generated drafts.
- **Optional Google Sheets integration** for lightweight operational reporting.
- **Manual HTML ingestion** for sites where automated retrieval is blocked or unreliable.

## Project status

This repository is an actively developed portfolio/product project. The core enrichment and analysis pipeline is functional, while production hardening and workflow features are being added incrementally.

Current focus:

- Enrichment reliability
- Opportunity-score calibration with real leads
- Human review workflow
- Production deployment and observability
- Safe email delivery and follow-up automation

AI output is currently **draft-only**. The application does not automatically send outreach emails.

## Architecture

```text
lead-intel/
├── ai/                 # Provider abstraction, routing, personalization
├── core/               # Database and domain models
├── crawlers/           # Website crawling and enrichment orchestration
├── ingestion/          # HTTP/Playwright website ingestion
├── processors/         # HTML, business, and opportunity analysis
├── templates/          # Intake and dashboard UI
├── tests/              # Automated tests
├── utils/              # Logging and integrations
├── app.py              # FastAPI web application
├── worker.py           # Background lead-processing worker
├── .env.example        # Environment configuration template
└── requirements.txt    # Python dependencies
```

## Requirements

- Python 3.11+ recommended
- Git
- Chromium/Playwright browser dependencies for browser fallback
- Google service-account credentials only if Google Sheets integration is enabled
- An AI provider API key only if AI drafting is enabled

## Quick start

### 1. Clone the repository

```bash
git clone https://github.com/han8zla/lead-intel.git
cd lead-intel
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
```

Linux systems may also need the Playwright OS dependencies:

```bash
python -m playwright install --with-deps chromium
```

### 4. Configure the environment

Copy `.env.example` to `.env` and add only the integrations you need.

```bash
cp .env.example .env
```

Never commit `.env`, API keys, service-account files, databases, or other credentials.

### 5. Start the API

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Then open:

- Intake: `http://localhost:8000/`
- Dashboard: `http://localhost:8000/dashboard`

### 6. Start the worker

In a second terminal, with the virtual environment activated:

```bash
python -m worker
```

The API queues leads in SQLite and the worker performs enrichment and analysis asynchronously.

## AI configuration

The AI layer uses OpenAI-compatible HTTP APIs and supports an ordered model pool. This keeps the application provider-agnostic and allows automatic failover.

Example:

```env
GROQ_API_KEY=your-key
GROQ_MODELS=openai/gpt-oss-20b,openai/gpt-oss-120b
GROQ_BASE_URL=https://api.groq.com/openai/v1
```

An optional second provider can be configured as well:

```env
OPENROUTER_API_KEY=your-key
OPENROUTER_MODELS=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

The router temporarily cools down models that return retryable failures such as HTTP 429 or 5xx responses and tries the next available model.

## Google Sheets integration

Google Sheets is optional. The integration expects a service-account credential file named `credentials.json` and a sheet named `Lead Intelligence` unless the implementation is configured differently.

Keep service-account credentials outside version control. The repository `.gitignore` already excludes credential files.

## Testing

Run the automated test suite with:

```bash
pytest -q
```

For a quick syntax check:

```bash
python -m py_compile app.py worker.py
```

The GitHub Actions workflow runs the test suite on pushes and pull requests.

## Operational notes

### Scraping reliability

The system intentionally uses HTTP before browser automation. This reduces resource usage and makes normal websites faster to process. Playwright is used when HTTP retrieval is unavailable or insufficient.

Some websites use bot protection, authentication, geolocation controls, or dynamic rendering. The platform supports manual HTML ingestion as a fallback, but it should not be used to bypass access controls.

### Data quality

Opportunity detection is evidence-driven. A missing social profile, for example, is not automatically treated as a valuable sales opportunity. Recommendations should be based on observable business signals and verified website content.

### Email safety

AI personalization generates drafts only. Human review should happen before any external outreach is sent. Any future email-sending workflow should include consent/compliance controls, rate limits, suppression lists, bounce handling, and audit logging.

## Production hardening roadmap

Before treating the application as a production service, complete the following:

- [ ] Add authentication and authorization for the dashboard and API.
- [ ] Move from SQLite to a managed relational database for multi-worker deployments.
- [ ] Add structured request IDs and centralized logs.
- [ ] Add health/readiness endpoints and monitoring.
- [ ] Add queue-backed worker execution and retry policies.
- [ ] Add outbound email compliance controls and audit trails.
- [ ] Add rate limiting for public API endpoints.
- [ ] Add automated dependency/security scanning.
- [ ] Add backup and recovery procedures.
- [ ] Validate opportunity-score thresholds against a representative lead dataset.

The repository is therefore **production-oriented, but not presented as a fully hardened public SaaS deployment yet**.

## Development workflow

Use feature branches for changes and keep commits focused. Run tests before opening a pull request.

Recommended flow:

```bash
git checkout -b feature/your-change
pytest -q
git add .
git commit -m "feat: describe the change"
git push -u origin feature/your-change
```

## Responsible use

Only process websites and business information that you are permitted to access and use. Respect applicable laws, website terms, robots policies where relevant, privacy requirements, and outreach regulations. Do not use this project to bypass authentication, access controls, or anti-abuse protections.

## License

No open-source license has been declared yet. Until a license is added, assume that the repository is available for viewing but is not granted for unrestricted reuse or redistribution.

## Maintainer

**Han8zla** — automation, lead intelligence, and AI workflow development.
