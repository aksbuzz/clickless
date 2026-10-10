# 0020. Shared API key authentication, and private internal services

- Status: Accepted
- Date: 2026-10-10 (updated the same day for the four-service stack)

## Context

The API had no authentication at all (audit F-03). Anyone who could reach port 8000, or port 3000 where nginx proxied every `/api/*` path, could create and run workflows, cancel instances, read `/metrics`, and read stored connection credentials in plaintext. Webhook endpoints failed open when their secret was empty (ADR 0009). The database and its neighbours were published on host ports with default credentials. The project owner chose a shared API key as the first step, over nginx basic auth or per-user logins.

## Decision

**Authentication.** Every API route requires `Authorization: Bearer <API_KEY>`, compared in constant time (`src/api/auth.py`). It is deny by default: a test walks `app.routes` and fails if any route lacks the dependency, apart from an explicit public list:

- `/ready` (container readiness probe), and
- `/triggers/{connector_id}/webhook`, which authenticates with the provider's own signature (ADR 0009).

`/health` and `/metrics` need the key. With no key configured, protected routes answer 503, and the API refuses to start unless `API_KEY` is at least 16 characters.

**UI.** The React app shows a key prompt before anything else (`ApiKeyGate`). It verifies the key against the API before accepting it, keeps it in `sessionStorage` (gone when the tab closes, never in `localStorage`), sends it with every request, and returns to the prompt on any 401 or on "Sign out".

**nginx.** The UI proxy exposes only what the UI uses. `/api/metrics`, `/api/triggers` and `/api/webhooks` return 404 through it (webhooks belong on the API port). It adds `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and a Content-Security-Policy, forwards `X-Forwarded-*`, and resolves the API at request time so a recreated container is picked up.

**Compose.** PostgreSQL is not published to the host. Every secret comes from `.env`, and Compose refuses to start with an empty one, with a message pointing at `scripts/init-env.sh`, which writes `.env` with random values (API key, database password and the key that encrypts stored credentials, ADR 0011) and prints the API key. The API and UI bind to `127.0.0.1` unless `BIND_ADDRESS` says otherwise. Adminer is behind the `dev-tools` profile and binds to localhost. Services wait for Postgres and restart unless stopped, and the API and worker have health checks.

**Checks.** `scripts/smoke.sh` asserts all of this against a running stack: 401 without or with a wrong key, a stored credential never returned by the API, unsigned webhooks rejected, the webhook and metrics paths not reachable through the UI proxy, the database port closed, a workflow that calls the internal API service fails as blocked (ADR 0021), and the seeded workflow still completes.

## Alternatives considered

- nginx basic auth in front of everything: no application code, but webhook routes need exemptions, there is no key for API clients, and nothing protects port 8000.
- Per-user accounts with JWT or an OIDC provider: needed for several users, roles or tenants, and the largest change (user store or provider, login screens, per-user audit).
- A key per client or per workflow: finer revocation, more machinery; a possible next step.

## Consequences

Positive:

- No unauthenticated access to any state-changing, secret-returning or operational route, and no public exposure of the database or admin tools.
- Fails closed at start-up and at request time, and a new route cannot be added without auth unnoticed.
- A fresh clone is safe by default: no shared default passwords exist.

Negative / follow-up:

- One shared secret means no per-user identity, no audit trail of who did what, and rotation affects everyone (change `API_KEY`, restart, re-enter it in the UI).
- The key is held in browser JavaScript for the session, so an XSS bug would expose it; the CSP and the absence of raw HTML injection reduce that risk.
- No rate limiting or lockout on key guesses; the 24-byte random key makes guessing impractical, but the endpoint should sit behind TLS and, ideally, a rate limiter.
- Plain HTTP between the browser and nginx: use TLS in front for anything beyond localhost.
- Connection credentials are encrypted at rest and never returned by the API (ADR 0011), but anyone with the key can still run steps that use them.
- An existing `.env` needs `API_KEY` and `SECRETS_KEY` (`sh scripts/init-env.sh --upgrade` adds the latter without touching the rest); the old `RABBITMQ_*` and `REDIS_*` settings are no longer used.

## References

- `src/api/auth.py`, `src/api/main.py`, `tests/unit/test_api_auth.py`
- `frontend/src/auth.ts`, `frontend/src/api.ts`, `frontend/src/components/ApiKeyGate.tsx`, `frontend/tests/`
- `docker-compose.yml`, `docker-compose.override.yml`, `frontend/nginx.conf`, `.env.example`, `scripts/init-env.sh`, `scripts/smoke.sh`
- Related: ADR 0009, ADR 0011, ADR 0021
