# 0009. Webhook trigger ingestion and per-provider signature verification

- Status: Accepted - under review (known gap: F-18; F-03 and F-04 fixed on 2026-10-10)
- Date: 2026-10-07 (recorded retrospectively)

## Context

External systems start workflows by calling the platform. These endpoints are public by nature, so each request must be authenticated against a provider-specific scheme before it can create work.

## Decision

Generic ingestion path, `POST /triggers/{connector_id}/webhook` (`src/api/routers/triggers.py`):

1. Look up the `TriggerHandlerPort` for the connector (404 if unknown).
2. Read the raw body and lower-cased headers; call `validate_webhook` (401 on failure; Slack `url_verification` challenges are answered directly).
3. `parse_events` turns the payload into normalised `TriggerEvent`s (unmapped events are acknowledged and ignored).
4. For each event, `process_external_trigger` finds active workflow versions by `(connector_id, trigger_id)` through the JSONB index, filters with `matches_workflow_config` (repository, branch, channel, board and so on), and creates one instance plus one outbox row per match in a single transaction (ADR 0002).

Verification per provider:

| Provider | Scheme | Secret source |
|---|---|---|
| GitHub | HMAC-SHA256 of the raw body, `X-Hub-Signature-256`, constant-time compare | env `GITHUB_WEBHOOK_SECRET` |
| Slack | v0 signing secret over `v0:{timestamp}:{body}`, 5 minute replay window | env `SLACK_SIGNING_SECRET` |
| Trello | base64 HMAC-SHA1 of the raw body plus the callback URL, `X-Trello-Webhook` (since 2026-10-10) | env `TRELLO_API_SECRET` and `TRELLO_CALLBACK_URL` |

Two further entry points exist for the `http` / `webhook` trigger types: `POST /webhooks/{workflow_name}` and `POST /workflows/{definition_name}/run`.

## Alternatives considered

- Per-connection secrets stored with the connection (ADR 0011) so each workflow or tenant has its own.
- Verify at an API gateway or reverse proxy and keep the app simple.
- Persist the raw webhook first and process it asynchronously, so the acknowledgement does not depend on database work (relevant to Slack's 3 second retry rule).
- Deduplicate by provider delivery id.

## Consequences

Positive:

- Raw-body HMAC with constant-time comparison is implemented correctly for GitHub and Slack.
- The port keeps provider parsing out of the service layer; handlers are plain functions of headers and bytes.

Negative / known gaps:

- Fixed on 2026-10-10 (F-04): verification now fails closed. With no secret configured, GitHub, Slack and Trello requests are rejected with 401, and Slack's `url_verification` handshake is answered only after its signature checks out. Previously an empty secret (the compose default) accepted forged events, and Trello was never verified. The Trello scheme follows Trello's documented webhook signing; confirm it against a real delivery. Signature comparisons are done on bytes, so a malformed header is a rejection rather than a crash.
- Fixed on 2026-10-10 (F-03): `POST /webhooks/{workflow_name}`, `/run` and everything under `/admin` now require the API key (ADR 0020).
- Secrets are global per provider, not per workflow.
- No deduplication: GitHub redeliveries and Slack retries (`X-Slack-Retry-Num`, `event_id`) each create a new instance (F-18).
- The route is `async def` but calls synchronous psycopg2 code, blocking the event loop in that worker for the duration of the database work (ADR 0012).

## References

- `src/api/routers/triggers.py`, `src/api/trigger_handlers/`
- `src/api/service.py` (`process_external_trigger`)
- `docker-compose.yml` (`api` environment)
- Related: ADR 0002, ADR 0008, ADR 0011
