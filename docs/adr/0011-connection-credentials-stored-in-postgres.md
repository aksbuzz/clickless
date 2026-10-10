# 0011. Connection credentials stored as JSONB in PostgreSQL

- Status: Accepted - under review (known gaps: F-03, F-05, F-06, F-19)
- Date: 2026-10-07 (recorded retrospectively)

## Context

Actions need credentials (GitHub token, Slack webhook URL, Trello key and token, PostgreSQL connection string). Users should enter them once and reuse them across workflows rather than pasting secrets into every step.

## Decision

Introduce a `connections` table (commit `dbfcdd5`): `id`, `connector_id`, `name` (unique per connector), `config JSONB`.

- Create and update validate that the connector exists and declares a `connection_schema`.
- A step references a connection with `connection_id`. The engine copies only the id into the action message.
- At execution time `WorkerService.execute_action` reads `connections.config` and merges it under the step's own config (step keys win), then the handler runs.
- `GET /connections` lists id, connector, name and timestamps only; `GET /connections/{id}` returns the full config.

Steps can also carry credentials inline in their `config` (the handlers accept `token`, `api_key`, `connection_string` and similar directly); those are stored in `workflow_versions.definition`.

## Alternatives considered

- Application-level encryption of `config` (AES-GCM with a key from the environment or a KMS). `pgcrypto` is already enabled in `init.sql`.
- External secret managers (Vault, AWS Secrets Manager). `boto3` is declared in `pyproject.toml` but not used.
- Write-only secrets: accept on create, never return, show masked values in the UI.
- Per-user or per-tenant ownership of connections.

## Consequences

Positive:

- Reuse and rotation in one place; secrets stay out of most workflow definitions when connections are used.
- The list endpoint does not leak config.

Negative / known gaps:

- Secrets are stored in plaintext and returned by `GET /connections/{id}`. With no authentication (F-03), any caller who can reach the API can read every credential. The frontend loads that config into the edit form and renders values as plain text inputs.
- The nginx container proxies all of `/api/`, so the same endpoint is reachable from the browser-facing port.
- Inline credentials are not stripped when a connection is selected in the builder, and definitions are displayed in the UI as JSON (F-19).
- Connection usage is not tracked: deleting a connection referenced by a workflow is allowed, and at run time the worker logs a warning and continues without it, so the step fails later with a confusing missing-field error.
- Templating is applied to the whole merged config, including SQL text in the PostgreSQL handlers, so values from triggers (for example an issue title) can alter the query (F-05). Handlers also call arbitrary caller-supplied URLs and connection strings, so a stored connection can be pointed at internal hosts (F-06).
- Secrets can end up in logs and history: the `log` handler writes the whole instance data at INFO, and each step execution stores full input and output snapshots (F-19).

## References

- `infrastructure/postgres/init.sql` (`connections`)
- `src/api/service.py`, `src/api/repository.py`, `src/api/routers/connections.py`
- `src/worker/service.py` (connection merge), `src/worker/handlers/`
- Related: ADR 0008, ADR 0009, ADR 0010
