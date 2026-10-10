# 0009. Webhook trigger ingestion and per-provider signature verification

- Status: Accepted - under review (known gap: deliveries are not de-duplicated)
- Date: 2026-10-07 (recorded after the fact; updated 2026-10-10)

## Context

External systems start workflows by calling the platform. These endpoints are public by nature, so each request must be authenticated against a provider-specific scheme before it can create work.

## Decision

Generic ingestion path, `POST /triggers/{connector_id}/webhook` (`src/api/routers/triggers.py`):

1. Look up the `TriggerHandlerPort` for the connector (404 if unknown).
2. Read the raw body and lower-cased headers; call `validate_webhook` (401 on failure; Slack `url_verification` challenges are answered only after their signature verifies).
3. `parse_events` turns the payload into normalised `TriggerEvent`s (unmapped events are acknowledged and ignored).
4. For each event, `process_external_trigger` finds active workflow versions by `(connector_id, trigger_id)` through the JSONB index, filters with `matches_workflow_config` (repository, branch, channel, board and so on), and creates one instance plus its first job per match, all in one transaction (`runtime.start_instance_for_version`, ADR 0018).

Verification per provider, **failing closed**: a request is rejected whenever the provider's secret is not configured.

| Provider | Scheme | Secret source |
|---|---|---|
| GitHub | HMAC-SHA256 of the raw body, `X-Hub-Signature-256`, constant-time compare | env `GITHUB_WEBHOOK_SECRET` |
| Slack | v0 signing secret over `v0:{timestamp}:{body}`, 5 minute replay window | env `SLACK_SIGNING_SECRET` |
| Trello | base64 HMAC-SHA1 of the raw body plus the callback URL, `X-Trello-Webhook` | env `TRELLO_API_SECRET` and `TRELLO_CALLBACK_URL` |

Signature comparisons are done on bytes, so a malformed header is a rejection rather than a crash. Two further entry points exist for the `http` / `webhook` trigger types, `POST /webhooks/{workflow_name}` and `POST /workflows/{definition_name}/run`; both require the API key (ADR 0020).

## Alternatives considered

- Per-connection secrets stored with the connection (ADR 0011) so each workflow or tenant has its own.
- Verify at an API gateway or reverse proxy and keep the app simple.
- Persist the raw webhook first and process it asynchronously, so the acknowledgement does not depend on database work (relevant to Slack's 3 second retry rule).
- Deduplicate by provider delivery id.

## Consequences

Positive:

- Raw-body HMAC with constant-time comparison for GitHub and Slack; Trello deliveries are verified too. Unsigned or unconfigured providers cannot start workflows.
- The port keeps provider parsing out of the service layer; handlers are plain functions of headers and bytes.
- Covered by tests that compute signatures independently of the code (`tests/unit/test_trigger_handlers.py`) and an end-to-end signed GitHub delivery (`tests/integration/test_api_flow.py`).

Negative / known gaps:

- Secrets are global per provider, not per workflow.
- The Trello scheme follows Trello's documentation; it has not been confirmed against a live delivery.
- No deduplication: GitHub redeliveries and Slack retries (`X-Slack-Retry-Num`, `event_id`) each create a new instance.
- The route is `async def` but calls synchronous database code, blocking the event loop in that worker for the duration of the database work (ADR 0012).
- The generic `/webhooks/{workflow_name}` route is protected by the shared API key, not a per-workflow token.

## References

- `src/api/routers/triggers.py`, `src/api/trigger_handlers/`
- `src/api/service.py` (`process_external_trigger`), `src/engine/runtime.py`
- `docker-compose.yml` (`api` environment)
- Related: ADR 0008, ADR 0011, ADR 0018, ADR 0020
