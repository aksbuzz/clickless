# 0008. Connector registry and trigger handler ports

- Status: Accepted - under review (known gaps: F-09, F-10)
- Date: 2026-10-07 (recorded retrospectively)

## Context

The product value is integrations (GitHub, Slack, Trello, PostgreSQL, HTTP, Python, flow control). Adding one should not require changes to the engine, and the UI must be able to discover what each integration offers (triggers, actions, config fields, connection fields) to render forms.

## Decision

Describe integrations declaratively on the API side, and implement execution separately on the worker side.

1. Catalogue (`src/shared/connectors/`): `Connector`, `ActionDefinition` and `TriggerDefinition` models, one definition file per connector under `definitions/`, registered in a module-level `ConnectorRegistry` when `definitions` is imported. The registry serves `GET /connectors` (UI forms), validates action ids on workflow save, and checks that a connector supports connections.
2. Execution (`src/worker/`): handler classes registered with the `@action("<action_id>")` decorator in `registry.py` into a dict keyed by `action_id`; the worker looks the handler up by that id.
3. Triggers: a port, `TriggerHandlerPort` (`validate_webhook`, `parse_events`, `matches_workflow_config`) in `src/shared/triggers/ports.py`, with GitHub, Slack and Trello implementations in `src/api/trigger_handlers/`, registered in `src/api/dependencies.py`.
4. Templating: `{{field.path}}` substitution is a shared helper (`src/shared/connectors/template.py`) that each handler calls itself.

To add a connector today: a definition file, a handler file, an import line in `worker/registry.py`, and optionally a trigger handler and its registration.

## Alternatives considered

- Co-locate schema and handler in one class so they cannot drift.
- Plugin discovery through entry points.
- Generic connectors generated from OpenAPI specs.
- Run connectors as separate services behind a common protocol.

## Consequences

Positive:

- The engine is connector-agnostic; the UI is data-driven.
- Trigger parsing is isolated behind a port and unit-testable.

Negative / known gaps:

- The two sides are linked only by the `action_id` string, with no startup or test check that every declared action has a handler. A mismatch becomes a runtime `Reject` and a stranded instance (F-08).
- Lookup is global by `action_id`, not `(connector_id, action_id)` as `docs/architecture.md` states; ids must be unique across connectors, and `connector_id` in a step is never checked.
- The `flow_control` connector declares `branch`, `delay` and `wait_for_event` as actions, but they are engine step types with no handler; using them as `type: action` passes validation and then fails at run time.
- Templating is opt-in per handler. `log`, `transform_data`, `http_request` and `send_webhook` in `src/worker/handlers/action_handlers.py` never call `resolve_config`, so `{{...}}` placeholders in the seed workflow and README examples are passed through literally (F-09). Where it is applied, it substitutes into every string, including SQL text (ADR 0011, F-05).
- Legacy handlers `initial_step` and `final_step` have no connector definition.

## References

- `src/shared/connectors/`, `src/shared/triggers/`
- `src/worker/registry.py`, `src/worker/handlers/`
- `src/api/trigger_handlers/`, `src/api/dependencies.py`
- Related: ADR 0004, ADR 0009
