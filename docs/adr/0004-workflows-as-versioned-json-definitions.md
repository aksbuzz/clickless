# 0004. Workflows as versioned JSON documents in PostgreSQL

- Status: Accepted - under review (known gap: definitions are not fully validated when saved)
- Date: 2026-10-07 (recorded after the fact; updated 2026-10-10)

## Context

Users build workflows in a UI (and through the API) at runtime. The system must run many instances of a workflow concurrently while the definition keeps being edited, and must find workflows by trigger quickly when a webhook arrives.

## Decision

A workflow is a JSON document stored in `workflow_versions.definition` (JSONB):

- `workflows(id, name UNIQUE)` is the identity; `workflow_versions(workflow_id, version, definition, is_active)` holds immutable versions.
- Saving a new version deactivates the others and inserts `max(version) + 1` (`WorkflowManagementService.create_version`). Only the active version is started or matched by triggers.
- A `workflow_instance` is pinned to the `workflow_version_id` it started on, so edits never affect running instances.
- Trigger lookup uses an expression index on `definition->'trigger'->>'connector_id'` and `->>'trigger_id'` for active versions (`idx_versions_trigger`).
- Shape: `trigger`, `start_at`, and `steps` keyed by name. Step kinds (`src/engine/steps.py`): `action` (the default), `branch` (operators `eq neq gt gte lt lte contains exists` on dot paths), `delay` (any step carrying `duration_seconds`) and `wait_for_event`. Routing uses `next`, or `on_true` / `on_false` for branches, with the terminal name `end`. Per-step `retry {max_attempts, delay_seconds}` (default one attempt) and optional `connection_id`.
- On create, `ConnectorRegistry.validate_definition` checks that each action step's `action_id` is known.
- The engine interprets the definition at run time (`src/engine/runtime.py`): it loads the pinned version with the instance on every step.

## Alternatives considered

- Workflows as code (Temporal, Airflow style): maximum power, but not editable by non-developers in a UI.
- YAML files in git: good review story, poor fit for a runtime builder and for per-instance version pinning.
- Normalised graph tables (steps and edges): enforces referential integrity in the database, at the cost of heavier writes and a more complex builder API.
- BPMN or a standard DSL: interoperable, but much larger scope.

## Consequences

Positive:

- Runtime editable, trivially versioned, and one row read gives the engine everything it needs.
- Pinning instances to versions removes migration concerns for in-flight work.

Negative / known gaps:

- Integrity is only as good as API-side validation, which only checks that action ids exist (and skips steps without one). It does not check that `start_at`, `next`, `on_true` or `on_false` point at existing steps, nor detect cycles, unknown step types or missing required config.
- The engine makes those mistakes visible instead of hanging: a dangling target fails the instance with `step '...' is not defined`, and more than 100 branch or delay steps in a row fails it as a probable cycle. A loop through action steps has no per-instance step cap.
- `validate_definition` looks actions up by `action_id` alone and ignores the step's `connector_id`.
- The definition format has no schema version, so future format changes need a data migration.
- There is no API to re-activate an older version (roll back).
- Concurrent `create_version` calls can compute the same next version, and one fails with a unique violation surfaced as HTTP 500.

## References

- `infrastructure/postgres/init.sql` (`workflows`, `workflow_versions`, `idx_versions_trigger`)
- `src/api/service.py`, `src/api/repository.py`, `src/shared/connectors/registry.py`
- `src/engine/steps.py`, `src/engine/runtime.py`
- Related: ADR 0008, ADR 0018
