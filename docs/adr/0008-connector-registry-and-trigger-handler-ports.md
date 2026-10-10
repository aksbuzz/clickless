# 0008. Connector registry and trigger handler ports

- Status: Accepted - under review (known gaps listed below)
- Date: 2026-10-07 (recorded after the fact; updated 2026-10-10)

## Context

The product value is integrations (GitHub, Slack, Trello, PostgreSQL, HTTP, flow control). Adding one should not require changes to the engine, and the UI must be able to discover what each integration offers (triggers, actions, config fields, connection fields) to render forms.

## Decision

Describe integrations declaratively on the API side, and implement execution separately on the worker side.

1. **Catalogue** (`src/shared/connectors/`): `Connector`, `ActionDefinition` and `TriggerDefinition` models, one definition file per connector under `definitions/`, registered in a module-level `ConnectorRegistry` when `definitions` is imported. The registry serves `GET /connectors` (UI forms), validates action ids on workflow save, and checks that a connector supports connections.
2. **Execution** (`src/worker/`): handler classes registered with the `@action("<action_id>")` decorator in `registry.py` into a dict keyed by `action_id`. The engine looks the handler up by the step's action id and calls `execute(instance_id, data, config) -> ActionResult` (see `docs/worker-and-scheduler.md`).
3. **Templating** (`src/engine/steps.py`, `src/shared/connectors/template.py`): the engine resolves `{{field.path}}` in a step's config once, before calling any handler. A handler lists keys that must never be resolved in `untemplated_keys`; the PostgreSQL handlers do this for `query` and `connection_string` so data can only reach SQL as bound parameters.
4. **Triggers**: a port, `TriggerHandlerPort` (`validate_webhook`, `parse_events`, `matches_workflow_config`) in `src/shared/triggers/ports.py`, with GitHub, Slack and Trello implementations in `src/api/trigger_handlers/`, registered in `src/api/dependencies.py`.
5. **Outbound calls** by handlers go through `src/shared/net_guard.py` (ADR 0021).

To add a connector: a definition file, a handler file, an import line in `definitions/__init__.py` and in `worker/registry.py`, and optionally a trigger handler and its registration.

## Alternatives considered

- Co-locate schema and handler in one class so they cannot drift.
- Plugin discovery through entry points.
- Generic connectors generated from OpenAPI specs.
- Run connectors as separate services behind a common protocol.

## Consequences

Positive:

- The engine is connector-agnostic; the UI is data-driven.
- Trigger parsing is isolated behind a port and unit-testable.
- Templating is in one place, so a handler cannot forget it or apply it twice.

Negative / known gaps:

- The two sides are linked only by the `action_id` string, with no startup or test check that every declared action has a handler. A mismatch fails the step at run time with `no handler registered for action '...'`.
- Lookup is global by `action_id`, not `(connector_id, action_id)`; ids must be unique across connectors, and `connector_id` in a step is never checked.
- The `flow_control` connector declares `branch`, `delay` and `wait_for_event` as actions, but they are engine step kinds with no handler; using them as `type: action` passes validation and fails at run time.
- Two legacy handlers, `initial_step` and `final_step`, have no connector definition.
- Handlers are called concurrently from several threads and must be stateless; nothing enforces that.

## References

- `src/shared/connectors/`, `src/shared/triggers/`
- `src/worker/registry.py`, `src/worker/handlers/`, `src/engine/worker.py` (`execute_step`)
- `src/api/trigger_handlers/`, `src/api/dependencies.py`
- Related: ADR 0004, ADR 0009, ADR 0018, ADR 0021
