# 0020. Shared API key authentication, and private internal services

- Status: Accepted
- Date: 2026-10-10

## Context

The API had no authentication at all (audit F-03). Anyone who could reach port 8000, or port 3000 where nginx proxied every `/api/*` path, could create and run workflows, cancel instances, trigger recovery, read `/metrics`, and read stored connection credentials in plaintext. Webhook endpoints failed open when their secret was empty (F-04, ADR 0009). RabbitMQ (guest/guest), Redis (no password) and, in the dev override, adminer were published on every host interface (F-12). The project owner chose, on 2026-10-10, a shared API key as the first step, over nginx basic auth or per-user logins.

## Decision

**Authentication.** Every API route requires `Authorization: Bearer <API_KEY>`, compared in constant time (`src/api/auth.py`). It is deny by default: a test walks `app.routes` and fails if any route lacks the dependency, apart from an explicit public list:

- `/ready` (container readiness probe), and
- `/triggers/{connector_id}/webhook`, which authenticates with the provider's own signature (ADR 0009).

`/health` and `/metrics` need the key. With no key configured, protected routes answer 503, and the API refuses to start unless `API_KEY` is at least 16 characters.

**UI.** The React app shows a key prompt before anything else (`ApiKeyGate`). It verifies the key against the API before accepting it, keeps it in `sessionStorage` (gone when the tab closes, never in `localStorage`), sends it with every request, and returns to the prompt on any 401 or on "Sign out".

**nginx.** The UI proxy exposes only what the UI uses. `/api/admin`, `/api/metrics`, `/api/triggers` and `/api/webhooks` return 404 through it (webhooks belong on the API port). It adds `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and a Content-Security-Policy, forwards `X-Forwarded-*`, and resolves the API at request time so a recreated container is picked up.

**Compose.** RabbitMQ, Redis and PostgreSQL are not published. RabbitMQ and Redis require passwords. Every secret comes from `.env`, and Compose refuses to start with an empty one, with a message pointing at `scripts/init-env.sh`, which writes `.env` with random values and prints the API key. The API and UI bind to `127.0.0.1` unless `BIND_ADDRESS` says otherwise. Adminer moved behind the `dev-tools` profile and binds to localhost; the dev override publishes the RabbitMQ management UI on localhost only. Services wait for Postgres, restart unless stopped, and the API has a health check. Celery no longer stores task results in a hardcoded unauthenticated Redis (nothing reads them), which also lets Redis have a password.

**Checks.** `scripts/smoke.sh` asserts all of this against a running stack: 401 without or with a wrong key, unsigned webhooks rejected, admin and metrics not reachable through the UI, the broker, cache and database ports closed, a workflow that calls the internal RabbitMQ admin API fails as blocked (ADR 0021), and the seeded workflow still completes.

## Alternatives considered

- nginx basic auth in front of everything: no application code, but webhook routes need exemptions, there is no key for API clients, and nothing protects port 8000.
- Per-user accounts with JWT or an OIDC provider: needed for several users, roles or tenants, and the largest change (user store or provider, login screens, per-user audit).
- A key per client or per workflow: finer revocation, more machinery; a possible next step.

## Consequences

Positive:

- Closes unauthenticated access to every state-changing, secret-returning and operational route (F-03), and the public exposure of the broker, cache and admin tools (F-12, F-25).
- Fails closed at start-up and at request time, and a new route cannot be added without auth unnoticed.
- A fresh clone is safe by default: no shared default passwords exist.

Negative / follow-up:

- One shared secret means no per-user identity, no audit trail of who did what, and rotation affects everyone (change `API_KEY`, restart, re-enter it in the UI).
- The key is held in browser JavaScript for the session, so an XSS bug would expose it; the CSP and the absence of raw HTML injection reduce that risk.
- No rate limiting or lockout on key guesses; the 24-byte random key makes guessing impractical, but the endpoint should sit behind TLS and, ideally, a rate limiter.
- Plain HTTP between the browser and nginx: use TLS in front for anything beyond localhost.
- Connection credentials are still stored in plaintext and returned by `GET /connections/{id}` to anyone with the key; masking and encryption at rest remain open (ADR 0011).
- Pre-existing deployments must run `scripts/init-env.sh` (or add the new variables) before upgrading. Redis and RabbitMQ credentials change, so existing volumes keep working only if those services are recreated with the new passwords.

## References

- `src/api/auth.py`, `src/api/main.py`, `tests/unit/test_api_auth.py`
- `frontend/src/auth.ts`, `frontend/src/api.ts`, `frontend/src/components/ApiKeyGate.tsx`, `frontend/tests/`
- `docker-compose.yml`, `docker-compose.override.yml`, `frontend/nginx.conf`, `.env.example`, `scripts/init-env.sh`, `scripts/smoke.sh`
- `docs/audit-2026-10-07.md` (F-03, F-12, F-25), ADR 0009, ADR 0011, ADR 0021
