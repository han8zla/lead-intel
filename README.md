# Lead Intelligence Platform

> Evidence-driven website intelligence for discovering business capabilities, unknown signals, workflow opportunities, and AI-assisted automation insights.

[![CI](https://github.com/han8zla/lead-intel/actions/workflows/ci.yml/badge.svg)](https://github.com/han8zla/lead-intel/actions/workflows/ci.yml)

Lead Intelligence started as a simple website enrichment experiment: fetch a business website, extract useful text and contacts, detect a few signals, and turn those signals into an opportunity score.

It has evolved into something substantially broader.

The current direction is an **observable, evidence-driven website intelligence platform** that treats a website as a source of business and technical evidence rather than simply a page of text. The system is being designed to discover pages, inspect HTML/DOM structure and attributes, preserve unfamiliar observations, identify known and unknown signals, build a contextual intelligence profile, use AI for reasoning where deterministic rules are insufficient, validate opportunities against evidence, and keep an auditable record of what happened during every analysis run.

> **Core principle:** observe first, preserve evidence, interpret second, recommend only when the evidence supports it.

---

## Project evolution

The project has intentionally changed direction as real websites exposed the limitations of a simple scraper-and-score model.

```text
Original idea
─────────────
Website → body text → signals → score

        ↓ real-world testing

Enrichment platform
────────────────────
Website → HTTP/Playwright → contacts → business signals → opportunities

        ↓ Phase 4 redesign

Intelligence platform
─────────────────────
Website
  ↓
Site discovery
  ↓
Deep HTML / DOM extraction
  ├─ text
  ├─ metadata
  ├─ headings
  ├─ links / hrefs
  ├─ buttons / CTAs
  ├─ forms / fields / attributes
  ├─ ARIA / data-* attributes
  ├─ JSON-LD / structured data
  ├─ scripts / iframes / external domains
  └─ technology evidence
  ↓
Evidence store
  ↓
Signal engine
  ├─ known signals
  └─ unknown signals
  ↓
Business intelligence profile
  ↓
AI reasoning / interpretation
  ↓
Opportunity candidates
  ↓
Evidence validation
  ↓
Priority / confidence
  ↓
Dashboard + audit trail
```

This evolution is intentional. The repository is no longer being treated as a one-off scraper; it is being developed as a portfolio-grade architecture exercise for observable AI-assisted automation systems.

---

## What the platform is becoming

The target system is designed around several cooperating layers:

| Layer | Responsibility |
|---|---|
| **Discovery** | Find relevant pages and understand site structure. |
| **Extraction** | Capture text, DOM structure, attributes, metadata, forms, links, scripts, structured data, and technology evidence. |
| **Evidence** | Preserve the source and context behind every meaningful observation. |
| **Signal Engine** | Convert raw observations into known, unknown, and contextual signals. |
| **Unknown Registry** | Preserve unfamiliar widgets, technologies, patterns, and behaviors instead of discarding them. |
| **Business Intelligence** | Build a compact representation of the business, audiences, services, capabilities, and workflows. |
| **AI Analysis** | Interpret ambiguous evidence and reason about business workflows without receiving unnecessary raw HTML. |
| **Opportunity Engine** | Produce evidence-backed automation candidates rather than generic feature-based recommendations. |
| **Validation** | Check confidence, evidence quality, existing capabilities, unknowns, and solution fit. |
| **Observability** | Record logs, metrics, traces, failures, recovery attempts, and audit events. |
| **Dashboard** | Make the entire analysis understandable to both humans and engineers. |

---

## Phase 4 — AI Business Intelligence & Opportunity Analysis

**Phase 4 is the current major development phase.** It is being redesigned as an intelligence and observability layer rather than another collection of scoring rules.

### Target analysis pipeline

```text
┌───────────────┐
│    Website    │
└───────┬───────┘
        ↓
┌────────────────────┐
│ Site Discovery     │  pages, links, sitemap, navigation
└────────┬───────────┘
         ↓
┌────────────────────┐
│ Deep Extraction    │  DOM, forms, attributes, metadata, tech
└────────┬───────────┘
         ↓
┌────────────────────┐
│ Evidence Layer     │  provenance + context + confidence
└────────┬───────────┘
         ↓
┌────────────────────┐
│ Signal Engine      │  known + unknown signals
└────────┬───────────┘
         ↓
┌────────────────────┐
│ Business Profile   │  audiences, services, capabilities, journey
└────────┬───────────┘
         ↓
┌────────────────────┐
│ AI Reasoning       │  interpretation + workflow analysis
└────────┬───────────┘
         ↓
┌────────────────────┐
│ Opportunity Engine │  candidates + evidence + unknowns
└────────┬───────────┘
         ↓
┌────────────────────┐
│ Validation         │  confidence + impact + solution fit
└────────┬───────────┘
         ↓
┌────────────────────┐
│ Priority           │  explainable prioritization
└────────┬───────────┘
         ↓
┌────────────────────┐
│ Dashboard / Audit  │  visual analysis + system history
└────────────────────┘
```

### Evidence-first intelligence

The system should not make conclusions directly from a single keyword.

For example:

```text
"Book Appointment"
       +
/appointments/
       +
external scheduler
       +
appointment-related form
       ↓
Appointment Booking
       ↓
Existing capability confirmed
       ↓
Do NOT automatically recommend building booking
       ↓
Investigate reminders, rescheduling, cancellation,
no-show recovery, and downstream workflow integration
```

This distinction is central to the project: **a capability already visible on a website is evidence that something exists, not proof that the underlying business workflow is automated.**

### Unknown signals

Unknown observations are first-class data.

```text
Unknown widget
   ↓
Preserve URL + script + attributes + nearby context
   ↓
Attempt deterministic classification
   ↓
AI interpretation when necessary
   ↓
Confidence + evidence
   ↓
Human validation
   ↓
Signal registry
   ↓
Future analyses can recognize the pattern
```

This creates a feedback loop for the intelligence layer without pretending that every new observation immediately changes model weights.

---

## Observability and auditability

The system is being designed so that failures are diagnosable, not merely logged as generic errors.

Each analysis will have an **analysis run ID** connecting discovery, extraction, evidence, signals, AI calls, opportunities, and scoring.

Planned event categories include:

```text
analysis.started
crawl.page_discovered
crawl.page_fetched
crawl.page_failed
crawl.fallback_started
extraction.completed
form.detected
technology.detected
evidence.created
signal.created
signal.updated
signal.rejected
unknown.detected
ai.analysis.started
ai.analysis.completed
ai.validation.completed
opportunity.created
opportunity.rejected
score.calculated
analysis.completed
analysis.failed
```

The long-term observability model separates:

- **Logs** — what the application and its components are doing.
- **Audit events** — what decisions and state changes occurred.
- **Metrics** — how healthy and efficient the system is.
- **Traces** — where time and failures occur across an analysis run.

A failed analysis should be able to answer:

> What failed? Where did it fail? What evidence was affected? Was recovery attempted? Did the system continue with partial data? How trustworthy is the final result?

---

## Planned dashboard

The dashboard is evolving from a simple lead table into an analysis workstation.

### 1. Command Center

System health, analysis throughput, failure rate, AI availability, unknown signals, validation backlog, and recent runs.

### 2. Analysis Pipeline

A visual step-by-step view:

```text
Discovery → Extraction → Evidence → Signals → AI → Opportunities → Validation → Priority
```

Each stage should be inspectable.

### 3. Intelligence Graph

A visual relationship between:

```text
Business
 ├── Pages
 ├── Technologies
 ├── Capabilities
 ├── Signals
 ├── Evidence
 ├── Unknowns
 ├── Workflows
 └── Opportunities
```

### 4. Opportunities

Each opportunity should explain:

- the observed problem or workflow
- supporting evidence
- existing capabilities
- unknowns
- impact
- confidence
- Handyman solution fit
- recommended next investigation

### 5. Audit & Observability

An analysis timeline with logs, failures, retries, recovery attempts, AI calls, signal decisions, and opportunity decisions.

---

## Current technology

The core remains deliberately lightweight:

- **Python 3.11+**
- **FastAPI / Uvicorn**
- **HTTPX**
- **BeautifulSoup / lxml**
- **Playwright** for browser fallback
- **SQLite** for the current portfolio-scale persistence layer
- **Jinja2 / HTML** for the current dashboard
- **pytest** for automated testing
- **OpenAI-compatible AI providers** through the internal provider/router abstraction
- **Google Sheets** as an optional operational integration

The architecture is intentionally a **modular monolith** for now. That gives the project clear boundaries without introducing distributed-system complexity before it solves a real problem. The system can later evolve toward separate workers, queues, services, managed databases, and dedicated observability infrastructure if scale requires them.

---

## AI architecture

AI is a reasoning layer, not the scraper.

The intended flow is:

```text
Raw website
     ↓
Local deterministic extraction
     ↓
Normalized evidence
     ↓
Compact business-intelligence JSON
     ↓
AI interpretation
     ↓
Strict structured output
     ↓
Validation
     ↓
Human-readable intelligence
```

The goal is **semantic compression**, not simply sending less text. Large raw HTML should be reduced locally into meaningful, traceable evidence before it reaches the model.

AI should be allowed to say:

```text
Insufficient evidence.
Recommend deeper investigation.
```

That is preferable to generating a confident opportunity from weak evidence.

The current AI router supports ordered model pools and automatic failover across configured OpenAI-compatible providers when retryable failures occur.

---

## Current capabilities already implemented

- HTTP-first website ingestion with Playwright fallback.
- Same-domain relevant subpage discovery.
- Contact extraction for business emails and phones.
- Manual HTML ingestion for difficult sites.
- Business signal extraction for common website capabilities.
- Evidence-aware opportunity detection foundation.
- Business-intelligence profile generation foundation.
- Persistent opportunity analysis in SQLite.
- Dashboard pipeline and lead reporting.
- OpenAI-compatible provider abstraction.
- Multi-model AI failover with retry/cooldown behavior.
- AI outreach drafts remain draft-only and are not automatically sent.
- Automated test suite and GitHub Actions CI workflow.
- Repository documentation, contribution guidance, security guidance, and development conventions.

The current Phase 4 branch is the architectural transition point toward the deeper evidence, unknown-signal, observability, and AI-analysis system described above.

---

## Requirements

- Python 3.11+ recommended
- Git
- Chromium/Playwright browser dependencies for browser fallback
- Google service-account credentials only if Google Sheets integration is enabled
- An AI provider API key only if AI analysis or drafting is enabled

---

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

Linux systems may also need:

```bash
python -m playwright install --with-deps chromium
```

### 4. Configure the environment

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

In a second terminal:

```bash
python -m worker
```

The API queues leads in SQLite and the worker performs enrichment and analysis asynchronously.

---

## AI configuration

Example Groq configuration:

```env
GROQ_API_KEY=your-key
GROQ_MODELS=openai/gpt-oss-20b,openai/gpt-oss-120b
GROQ_BASE_URL=https://api.groq.com/openai/v1
```

Optional OpenRouter configuration:

```env
OPENROUTER_API_KEY=your-key
OPENROUTER_MODELS=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

The router temporarily cools down models that return retryable failures such as HTTP 429 or 5xx responses and tries the next available model.

---

## Testing

Run:

```bash
pytest -q
```

For a quick syntax check:

```bash
python -m py_compile app.py worker.py
```

The GitHub Actions workflow runs the automated test suite on pushes and pull requests.

---

## Engineering roadmap

### Phase 1 — Foundation
- [x] Initial lead ingestion and persistence
- [x] Core data models
- [x] Basic processing workflow

### Phase 2 — Website Enrichment
- [x] HTTP-first ingestion
- [x] Contact extraction
- [x] Relevant subpage discovery
- [x] Browser fallback
- [x] Manual HTML ingestion

### Phase 3 — Lead Intelligence Dashboard
- [x] Lead pipeline
- [x] Lead details
- [x] Opportunity reporting
- [x] AI draft visibility
- [x] Operational statistics

### Phase 4 — AI Business Intelligence & Opportunity Analysis **(current)**
- [x] Evidence-oriented opportunity foundation
- [x] Business-intelligence profile foundation
- [x] AI provider/router foundation
- [ ] Deep DOM and attribute extraction
- [ ] Structured data / JSON-LD intelligence
- [ ] Technology and integration detection
- [ ] Evidence/provenance model
- [ ] Unknown signal registry
- [ ] Signal validation workflow
- [ ] Analysis run model
- [ ] Structured audit events
- [ ] Metrics and tracing
- [ ] AI business analyst
- [ ] AI opportunity validation
- [ ] Explainable priority model
- [ ] Analysis pipeline visualization
- [ ] Intelligence graph
- [ ] Audit / observability dashboard
- [ ] Real-lead validation across the collected dataset

### Phase 5 — Outreach Intelligence
- [ ] Human-reviewed outreach workflow
- [ ] Personalized campaign preparation
- [ ] Lead segmentation
- [ ] Follow-up planning
- [ ] Compliance and suppression controls

### Phase 6 — Workflow Automation
- [ ] Triggered workflows
- [ ] External system integrations
- [ ] Task and notification automation
- [ ] Workflow execution history

### Phase 7 — Production Platform
- [ ] Authentication / authorization
- [ ] Managed relational database
- [ ] Queue-backed workers
- [ ] Centralized observability
- [ ] Rate limiting
- [ ] Security scanning
- [ ] Backups and recovery
- [ ] Production deployment architecture

> The phase numbers are product milestones, not a claim that every feature in an earlier phase is production-hardened. Phase 4 is deliberately absorbing several ideas that originally appeared to belong to later phases because the intelligence layer now determines the quality of everything built on top of it.

---

## Production hardening

Before treating the application as a production service, the following remain important:

- Authentication and authorization
- Managed relational storage for multi-worker deployments
- Queue-backed execution and retry policies
- Centralized structured logs
- Metrics, tracing, and alerting
- Health/readiness endpoints
- Rate limiting
- Security/dependency scanning
- Backup and recovery procedures
- Outreach compliance controls
- Opportunity calibration against representative outcomes

The repository is therefore **production-oriented, but not presented as a fully hardened public SaaS deployment**.

---

## Responsible use

Only process websites and business information that you are permitted to access and use. Respect applicable laws, website terms, robots policies where relevant, privacy requirements, and outreach regulations. Do not use this project to bypass authentication, access controls, or anti-abuse protections.

AI-generated analysis is decision support, not a guarantee that a business will purchase or benefit from a proposed automation. Human review remains important, especially when evidence is incomplete.

---

## Development workflow

The current major redesign is developed on a dedicated Phase 4 branch before it becomes the new `main` baseline.

Recommended workflow:

```bash
git checkout -b feature/your-change
pytest -q
git add .
git commit -m "feat: describe the change"
git push -u origin feature/your-change
```

Large architectural changes should be reviewed and merged as coherent milestones rather than replacing the stable baseline with partially implemented work.

---

## License

No open-source license has been declared yet. Until a license is added, assume that the repository is available for viewing but is not granted for unrestricted reuse or redistribution.

## Maintainer

**Han8zla** — automation, lead intelligence, and AI workflow development.
