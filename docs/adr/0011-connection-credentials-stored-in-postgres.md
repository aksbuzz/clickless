# 0011. Connection credentials: write-only and encrypted in PostgreSQL

- Status: Accepted - under review (known gaps: credentials typed into a step instead of a connection are not protected, and the key lives beside the database URL)
- Date: 2026-10-07 (recorded after the fact; rewritten 2026-10-10 when credentials became write-only and encrypted)

## Context

Actions need credentials (GitHub token, Slack webhook URL, Trello key and token, PostgreSQL connection string). Users should enter them once and reuse them across workflows rather than pasting secrets into every step.

Until now they were stored as plain JSON and `GET /connections/{id}` returned them, so anyone holding the API key could read every token, and a database dump or backup exposed all of them (audit F-03, F-19).

## Decision

A `connections` table: `id`, `connector_id`, `name` (unique per connector), `config JSONB`. A step references a connection with `connection_id`; when the engine begins the step it merges the connection's config under the step's own config (step keys win). If the connection no longer exists the step fails with a clear message before the handler runs.

**Secret fields.** A connector marks its credential fields `"writeOnly": true` in `connection_schema`. All four connectors do. A test lists the fields per connector and fails when a connector with a connection schema is added without being listed.

**Validation.** Creating or updating a connection checks the config against the schema: unknown fields are rejected (so nothing unprotected can be stored under a name the schema does not know), string fields must be text, and required fields must hold a value. Problems come back as a `validation_errors` list.

**Encrypted at rest.** `src/shared/credentials.py` encrypts each secret value with Fernet (AES-128-CBC with an HMAC-SHA256 check) and stores it as `enc:v1:<token>` inside the JSONB. Non-secret fields stay readable. Every encryption produces a different token, and a changed or wrongly keyed token fails to decrypt instead of returning garbage.

**Write-only API.** `GET /connections/{id}` returns `config` with the non-secret fields only, plus `secrets_set`, the names of the secret fields that hold a value. The list endpoint never returned config. On update, a secret that is left out or blank keeps its stored value and a non-blank one replaces it; non-secret fields come from the request alone. If a connection's connector is no longer registered, every field is treated as secret. There is no way to clear an optional secret other than deleting the connection.

**Decrypted only where used.** `runtime.begin_step` decrypts in memory, for that step, and hands the result to the handler. If a value cannot be decrypted (wrong or missing key) the step fails before the handler runs, with a message that names `SECRETS_KEY`.

**The key.** `SECRETS_KEY` holds one Fernet key, or several separated by commas: the first encrypts and all decrypt. The API and the worker refuse to start without a valid key. `scripts/init-env.sh` creates one, and `sh scripts/init-env.sh --upgrade` adds one to an existing `.env`.

- To encrypt rows written before this change, or to move everything to a new key, run `docker compose run --rm api python -m src.api.encrypt_connections`. It re-encrypts every secret with the first key, is safe to repeat, and either updates all connections or (if any value cannot be decrypted) none.
- To rotate: put the new key first (`SECRETS_KEY=new,old`), restart, run the command, then drop the old key.
- Until the command runs, a stored value without the `enc:v1:` tag is read as legacy plaintext, so an upgrade does not break existing workflows. Saving a connection encrypts it.

**UI.** Secret fields are password inputs. When a secret is already stored the form shows a "saved" marker and "Leave blank to keep it", and sends nothing for it unless the user types a new value.

## Alternatives considered

- Encrypting in SQL with `pgcrypto`. The key would pass through SQL statements, which PostgreSQL can log, and the database would hold both key and data.
- An external secret manager or KMS (Vault, AWS Secrets Manager). Separates the key from the host and gives audit and rotation, at the cost of another service to run. A sensible next step; the `credentials` module is the one place that would change.
- Keeping the values readable but hiding them in the UI only. The API would still return them.
- Per-user or per-tenant ownership of connections.

## Consequences

Positive:

- A database dump, a backup, a read-only SQL injection or a stray `SELECT` shows ciphertext, and the API no longer returns a secret to anyone, including key holders.
- Reuse and rotation in one place; secrets stay out of workflow definitions when a connection is used.
- Existing databases keep working through the upgrade.

Negative / known gaps:

- `SECRETS_KEY` sits in the same `.env` and process environment as `DATABASE_URL`. This protects data at rest and in the API, not against someone who can read the container's environment. Losing the key loses the credentials: they would have to be entered again, so keep a copy of `.env`.
- Anyone with the API key can still use a credential (run a step that uses the connection), only not read it.
- Credentials typed directly into a step's config (handlers still accept `token`, `api_key`, `connection_string` and similar) are stored in plaintext in `workflow_versions.definition` and shown in the UI as JSON.
- Secrets that an earlier step puts into the instance data are stored in `workflow_instances.data`, and the `log` handler writes the whole instance data at INFO.
- Connection usage is not tracked: deleting a connection that a workflow references is allowed, and the step then fails at run time.
- The Fernet token format is versioned only through the `enc:v1:` tag; a change of algorithm needs a new tag and a migration.

## References

- `src/shared/credentials.py`, `src/api/encrypt_connections.py`
- `src/api/service.py` (connections), `src/api/routers/connections.py`, `src/engine/runtime.py` (`begin_step`)
- `src/shared/connectors/definitions/` (`connection_schema`)
- `infrastructure/postgres/init.sql` (`connections`), `scripts/init-env.sh`, `.env.example`
- `tests/unit/test_credentials.py`, `tests/unit/test_connection_schemas.py`, `tests/integration/test_connections.py`, `tests/integration/test_encrypt_connections.py`, `scripts/smoke.sh`
- Related: ADR 0008, ADR 0009, ADR 0020, ADR 0021
