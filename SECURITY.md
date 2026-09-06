# Security Policy

## Scope

Lead Intelligence can process business websites, contact information, AI-provider credentials, and optional Google service-account credentials. Treat all of these as potentially sensitive operational data.

## Reporting a vulnerability

Please do not publish credentials or exploit details in a public issue.

For a private report, contact the repository maintainer through the GitHub account associated with this project. Include a short description, affected component, reproduction steps, and potential impact when possible.

## Secrets

Never commit:

- `.env` files;
- API keys or access tokens;
- `credentials.json` or other service-account files;
- session/cookie exports;
- production databases;
- logs containing personal or customer data.

If a secret is accidentally committed, revoke or rotate it immediately. Removing the file in a later commit does not make an exposed secret safe.

## Production deployment

Before exposing the application publicly, add authentication, API rate limiting, HTTPS, secure secret storage, centralized logging, database backups, and monitoring. The development dashboard should not be treated as a public unauthenticated service.
