# 0011. Connection credentials stored as JSONB in PostgreSQL

- Status: Accepted - under review (known gap: credentials are stored and returned in plaintext)
- Date: 2026-10-07 (recorded after the fact; updated 2026-10-10)

## Context

Actions need credentials (GitHub token, Slack webhook URL, Trello key and token, PostgreSQL connection string). Users should enter them once and reuse them across workflows rather than pasting secrets into every step.

## Decision

A `connections` table: `id`, `connector_id`, `name` (unique per connector), `config JSONB`.

- Create and update validate that the connector exists and declares a `connection_schema`.
- A step references a connection with `connection_id`.
- When the engine begins a step (`runtime.begin_step`), it reads `connections.config` and merges it under the step's own config (step keys win). If the connection no longer exists the step fails with a clear message before the handler runs.
- `GET /connections` lists id, connector, name and timestamps only; `GET /connections/{id}` returns the full config.

Steps can also carry credentials inline in their `config` (the handlers accept `token`, `api_key`, `connection_string` and similar directly); those are stored in `workflow_versions.definition`.

## Alternatives considered

- Application-level encryption of `config` (AES-GCM with a key from the environment or a KMS). `pgcrypto` is already enabled in `init.sql`.
- External secret managers (Vault, AWS Secrets Manager).
- Write-only secrets: accept on create, never return, show masked values in the UI.
- Per-user or per-tenant ownership of connections.

## Consequences

Positive:

- Reuse and rotation in one place; secrets stay out of most workflow definitions when connections are used.
- The list endpoint does not leak config.
- Only holders of the API key can read anything (ADR 0020); the nginx proxy does not expose anything outside the UI's routes.
- Step executions no longer store a copy of the instance data as input, so credentials that reached the data are not copied into every step row (they are still in `workflow_instances.data`).
- Values from triggers and earlier steps cannot alter SQL or choose the database (the SQL handlers never template `query` or `connection_string`), and handlers cannot reach internal hosts unless allowed (ADR 0021).

Negative / known gaps:

- Secrets are stored in plaintext and returned by `GET /connections/{id}` to anyone with the API key. The frontend loads that config into the edit form and renders values as plain text inputs.
- Inline credentials are not stripped when a connection is selected in the builder, and definitions are displayed in the UI as JSON.
- Connection usage is not tracked: deleting a connection that a workflow references is allowed, and the step then fails at run time.
- The `log` handler writes the whole instance data at INFO, which can include anything an earlier step returned.

## References

- `infrastructure/postgres/init.sql` (`connections`)
- `src/api/service.py`, `src/api/repository.py`, `src/api/routers/connections.py`
- `src/engine/runtime.py` (`begin_step`), `src/worker/handlers/`
- Related: ADR 0008, ADR 0009, ADR 0020, ADR 0021
