# 0023. Validate workflow definitions when they are saved

- Status: Accepted
- Date: 2026-10-10

## Context

A workflow is a JSON document the user writes in the builder or sends to the API (ADR 0004). Saving it checked only that each action step's `action_id` existed somewhere in the catalogue. The engine is forgiving about everything else, which turns a typo into a surprise long after the save:

- a `next`, `on_true` or `on_false` that names no step fails the run with "step is not defined" (a missing one silently ends the run);
- an unknown branch operator is simply false, so the branch always goes the same way;
- a bad `retry` value falls back to a default;
- a `start_at` that names nothing fails the run as soon as it starts;
- a step named `end` can never run, and a step name over 100 characters is rejected by the database column at run time;
- a branch and delay loop is stopped after 100 repeats with an error.

The builder made this easy to hit: a new step starts with empty `connector_id` and `action_id`, and nothing stopped it being saved (audit F-10, F-28).

## Decision

`validate_definition(definition, registry)` in `src/engine/validation.py` runs on both save paths, `create_workflow` and `create_version`, before anything is written. It never touches the database, it returns every problem it finds as a message for the person editing (the API answers HTTP 400 with the `validation_errors` list), and the definition is saved only when the list is empty.

What it checks:

- **Shape.** The definition and `steps` are objects, there is at least one step, each step is an object, and `inputs` (advisory) is a list of uniquely named objects.
- **Start and names.** `start_at` is given and names a step. A step name is not empty, not longer than 100 characters, and is not `end`, which means "finish the run".
- **Links.** Every `next` (action, delay, wait) and both `on_true` and `on_false` (branch) must be present and must name a step or `end`. A missing link is an error, with the hint that `end` finishes the run, so a misspelled key cannot silently end a workflow.
- **Step types.** The type is one of `action`, `branch`, `delay`, `wait_for_event`. A step with `duration_seconds` is a delay, as in the engine.
- **Actions.** `connector_id` and `action_id` are given, the connector exists, the action exists, and the action belongs to that connector. The `flow_control` entries (`branch`, `delay`, `wait_for_event`) are step types with no handler, and using one as an action is refused with a pointer to `type`. `config` is an object, `connection_id` is text, and `retry` has a whole `max_attempts` of at least 1 and a whole `delay_seconds` of 0 or more.
- **Branches.** `condition` is an object with a `field`, and `operator`, if given, is one the engine understands (`OPERATORS` in `src/engine/steps.py`; a test checks the engine evaluates each).
- **Delay and wait.** `duration_seconds` is a number of 0 or more; `timeout_seconds`, if given, is more than 0.
- **Trigger.** Optional. If present: an object with a known `connector_id`, a `trigger_id` that connector has, and an object `config`.
- **Loops.** A loop made only of branch and delay steps is refused. Those steps never change the data, so once a run is inside such a loop it cannot leave, and the engine would stop it after 100 repeats. Found with strongly connected components, so every such group is reported once.

Deliberately not checked:

- `event_name` on a wait step. The engine resumes whichever instance is waiting, whatever the name, so it is a label.
- That a `connection_id` exists, or belongs to the step's connector. It would need the database; a missing connection already fails the step with a clear message.
- That `config` holds every field the action needs. A connection supplies some, and the fields vary by connector.
- `{{templates}}`.
- Loops that pass through an action or wait step. A workflow that polls (check a status, branch, delay, check again) is a real use, and nothing static can tell it from a runaway.
- Steps that nothing links to. Harmless, and the builder can leave them while a workflow is being drawn.

The old `ConnectorRegistry.validate_definition` is removed; this function replaces it.

## Alternatives considered

- **JSON Schema for the document.** Good for the shape, but the graph rules (links, loops, action belongs to connector) need code anyway, and one place is easier to read.
- **Validate only in the UI.** The API is the boundary, and other clients exist.
- **Reject unreachable steps.** Draws attention to forgotten steps but blocks a half-drawn workflow.
- **A hard cap on steps per run**, to end loops through actions. Not decided: polling loops legitimately run for many iterations, so a default needs a view on how long they should be allowed to run. Left open.
- **Validate at run time too.** The engine already fails cleanly on what it cannot run; validating again on every step would cost work to catch what the save already caught.

## Consequences

Positive:

- A mistake is reported when the workflow is saved, all of them at once, in words that name the step and the field.
- The builder's empty new steps, a misspelled link, a bad operator and a loop that can never end can no longer be saved.
- The documentation examples are checked by a test, which found a README example that used an action that does not exist.

Negative / follow-up:

- **Stricter than before.** An API client that omitted `next` on a last step (relying on the engine's "no next means finish") is now refused until it writes `"next": "end"`.
- **Not retroactive.** Versions saved before this check are not re-validated and keep running as they did. They are checked the next time someone saves a new version of them.
- A loop through action steps has no limit, so a mistaken polling loop runs until cancelled.
- The builder still has no checks of its own: it learns about problems from the API's answer on save. The messages are shown one per line.
- Only existence and shape are checked, not whether a step's config makes sense.

## References

- `src/engine/validation.py`, `src/engine/steps.py` (`OPERATORS`), `src/api/service.py` (`create_workflow`, `create_version`)
- `tests/unit/test_definition_validation.py`, `tests/integration/test_workflow_validation.py`, `scripts/smoke.sh`
- `frontend/src/api.ts` (shows each message on its own line)
- Related: ADR 0004, ADR 0008, ADR 0018
