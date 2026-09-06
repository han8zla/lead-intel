# Contributing

Thanks for helping improve Lead Intelligence.

## Development setup

1. Create and activate a Python virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Install the Playwright browser with `python -m playwright install chromium`.
4. Copy `.env.example` to `.env` and configure only the integrations you need.

## Before submitting changes

Run:

```bash
pytest -q
python -m py_compile app.py worker.py
```

Keep credentials, databases, browser artifacts, logs, and local environment files out of commits.

## Branches and commits

Use a focused feature or fix branch. Prefer small, descriptive commits such as:

- `feat: add lead review endpoint`
- `fix: improve phone extraction`
- `test: cover dashboard statistics`
- `docs: update deployment guide`

## Pull requests

A pull request should explain:

- what changed;
- why the change was needed;
- how it was tested;
- any configuration or migration requirements;
- any known limitations.

For scraping changes, include representative test cases covering both normal websites and failure/challenge conditions.

## Security

Do not commit API keys, service-account credentials, cookies, session files, personal data, or production database files. Report security issues privately according to `SECURITY.md`.
