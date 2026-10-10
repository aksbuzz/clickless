"""Checks on a workflow definition, run when it is saved.

The engine tolerates a lot (a missing link ends the run, an unknown operator is simply false, a bad retry
setting falls back to a default), which is how a typo turns into a run that does something else or fails
long after the workflow was saved. ``validate_definition`` reports those mistakes at save time instead. It
returns every problem it finds, as messages for the person editing the workflow, and an empty list when the
definition is fine. It does not touch the database.

Deliberately not checked: ``event_name`` (the engine resumes whichever instance is waiting, whatever the name),
whether a ``connection_id`` exists, whether the config holds every field an action needs (a connection may
supply some), and loops that pass through an action or wait step (polling is a real use; see ADR 0023).
"""
from typing import Dict, List, Optional

from src.engine.steps import OPERATORS, STEP_KINDS

END = "end"
MAX_STEP_NAME = 100          # workflow_step_executions.step_name is VARCHAR(100)
CONTROL = ("branch", "delay")
FLOW_CONTROL = "flow_control"   # catalogue entry for the step types; it has no handlers


def _is_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_definition(definition, registry) -> List[str]:
    if not isinstance(definition, dict):
        return ["The workflow definition must be a JSON object"]
    errors: List[str] = []
    _check_trigger(definition.get("trigger"), registry, errors)
    _check_inputs(definition.get("inputs"), errors)

    steps = definition.get("steps")
    if not isinstance(steps, dict) or not steps:
        return errors + ["The workflow needs a 'steps' object with at least one step"]

    _check_start(definition.get("start_at"), steps, errors)
    graph: Dict[str, List[str]] = {}
    for name, step in steps.items():
        if not _check_name(name, errors):
            continue
        if not isinstance(step, dict):
            errors.append(f"Step '{name}' must be an object")
            continue
        kind = _kind(step)
        if kind is None:
            errors.append(f"Step '{name}': unknown type '{step.get('type')}' (use {', '.join(STEP_KINDS)})")
            continue
        targets = _check_step(name, step, kind, steps, registry, errors)
        if kind in CONTROL:
            graph[name] = targets
    _check_loops(graph, errors)
    return errors


def _kind(step: dict) -> Optional[str]:
    """The same rule as the engine: a step with a duration is a delay whatever its type says."""
    if "duration_seconds" in step:
        return "delay"
    declared = step.get("type")
    if declared is None:
        return "action"
    return declared if declared in STEP_KINDS else None


def _check_name(name, errors: List[str]) -> bool:
    if not isinstance(name, str) or not name.strip():
        errors.append("Step names cannot be empty")
        return False
    if name == END:
        errors.append("Step name 'end' is reserved: it means the run finishes")
        return False
    if len(name) > MAX_STEP_NAME:
        errors.append(f"Step name '{name[:30]}...' is longer than {MAX_STEP_NAME} characters")
        return False
    return True


def _check_start(start_at, steps: dict, errors: List[str]) -> None:
    if not _is_text(start_at):
        errors.append("'start_at' is required and must name the first step")
    elif start_at == END:
        errors.append("'start_at' cannot be \"end\"")
    elif start_at not in steps:
        errors.append(f"'start_at' names '{start_at}', which is not a step in this workflow")


def _link(name: str, step: dict, field: str, steps: dict, errors: List[str]) -> Optional[str]:
    target = step.get(field)
    if target is None:
        errors.append(f"Step '{name}': '{field}' is required (use \"end\" to finish the run)")
        return None
    if not isinstance(target, str):
        errors.append(f"Step '{name}': '{field}' must be the name of a step or \"end\"")
        return None
    if target != END and target not in steps:
        errors.append(f"Step '{name}': '{field}' points to '{target}', which is not a step in this workflow")
        return None
    return target


def _check_step(name: str, step: dict, kind: str, steps: dict, registry, errors: List[str]) -> List[str]:
    """Check one step and return the steps it can lead to."""
    if kind == "branch":
        _check_condition(name, step.get("condition"), errors)
        return [t for t in (_link(name, step, "on_true", steps, errors), _link(name, step, "on_false", steps, errors)) if t]

    if kind == "delay":
        if "duration_seconds" in step and (not _is_number(step["duration_seconds"]) or step["duration_seconds"] < 0):
            errors.append(f"Step '{name}': duration_seconds must be a number of seconds, 0 or more")
    elif kind == "wait_for_event":
        timeout = step.get("timeout_seconds")
        if timeout is not None and (not _is_number(timeout) or timeout <= 0):
            errors.append(f"Step '{name}': timeout_seconds must be more than 0 seconds (leave it out to wait without a limit)")
    else:
        _check_action(name, step, registry, errors)

    target = _link(name, step, "next", steps, errors)
    return [target] if target else []


def _check_condition(name: str, condition, errors: List[str]) -> None:
    if condition is None:
        errors.append(f"Step '{name}': condition is required")
        return
    if not isinstance(condition, dict):
        errors.append(f"Step '{name}': condition must be an object")
        return
    if not _is_text(condition.get("field")):
        errors.append(f"Step '{name}': condition.field is required")
    operator = condition.get("operator")
    if operator is not None and operator not in OPERATORS:
        errors.append(f"Step '{name}': unknown operator '{operator}' (use {', '.join(OPERATORS)})")


def _check_action(name: str, step: dict, registry, errors: List[str]) -> None:
    connector_id, action_id = step.get("connector_id"), step.get("action_id")
    connector = None
    if not _is_text(connector_id):
        errors.append(f"Step '{name}': connector_id is required")
    else:
        connector = registry.get_connector(connector_id)
        if connector is None:
            errors.append(f"Step '{name}': unknown connector_id '{connector_id}'")
    if not _is_text(action_id):
        errors.append(f"Step '{name}': action_id is required")
    elif connector_id == FLOW_CONTROL and action_id in STEP_KINDS:
        errors.append(f"Step '{name}': '{action_id}' is a step type, not an action; set \"type\" to \"{action_id}\" instead")
    elif registry.get_action(action_id) is None:
        errors.append(f"Step '{name}': unknown action_id '{action_id}'")
    elif connector is not None and not any(a.id == action_id for a in connector.actions):
        owner = next(c.id for c in registry.list_connectors() if any(a.id == action_id for a in c.actions))
        errors.append(f"Step '{name}': action_id '{action_id}' belongs to connector '{owner}', not '{connector_id}'")

    if step.get("config") is not None and not isinstance(step["config"], dict):
        errors.append(f"Step '{name}': config must be an object")
    if step.get("connection_id") is not None and not _is_text(step["connection_id"]):
        errors.append(f"Step '{name}': connection_id must be text")
    _check_retry(name, step.get("retry"), errors)


def _check_retry(name: str, retry, errors: List[str]) -> None:
    if retry is None:
        return
    if not isinstance(retry, dict):
        errors.append(f"Step '{name}': retry must be an object")
        return
    if "max_attempts" in retry and not (_is_whole(retry["max_attempts"]) and retry["max_attempts"] >= 1):
        errors.append(f"Step '{name}': retry.max_attempts must be a whole number, 1 or more")
    if "delay_seconds" in retry and not (_is_whole(retry["delay_seconds"]) and retry["delay_seconds"] >= 0):
        errors.append(f"Step '{name}': retry.delay_seconds must be a whole number of seconds, 0 or more")


def _check_trigger(trigger, registry, errors: List[str]) -> None:
    if trigger is None:
        return
    if not isinstance(trigger, dict):
        errors.append("trigger must be an object")
        return
    connector_id, trigger_id = trigger.get("connector_id"), trigger.get("trigger_id")
    for key, value in (("connector_id", connector_id), ("trigger_id", trigger_id)):
        if not _is_text(value):
            errors.append(f"trigger.{key} is required")
    if _is_text(connector_id) and _is_text(trigger_id):
        connector = registry.get_connector(connector_id)
        if connector is None:
            errors.append(f"trigger.connector_id '{connector_id}' is not a known connector")
        elif not any(t.id == trigger_id for t in connector.triggers):
            errors.append(f"trigger.trigger_id '{trigger_id}' is not a trigger of connector '{connector_id}'")
    if trigger.get("config") is not None and not isinstance(trigger["config"], dict):
        errors.append("trigger.config must be an object")


def _check_inputs(inputs, errors: List[str]) -> None:
    if inputs is None:
        return
    if not isinstance(inputs, list):
        errors.append("inputs must be a list")
        return
    seen = set()
    for index, item in enumerate(inputs):
        if not isinstance(item, dict):
            errors.append(f"inputs[{index}] must be an object")
        elif not _is_text(item.get("name")):
            errors.append(f"inputs[{index}].name is required")
        elif item["name"] in seen:
            errors.append(f"inputs: '{item['name']}' is listed twice")
        else:
            seen.add(item["name"])


def _check_loops(graph: Dict[str, List[str]], errors: List[str]) -> None:
    """Report loops that contain only branch and delay steps. They never change the data, so once a run enters
    one it cannot leave, and the engine would stop it with an error after repeating."""
    edges = {node: [t for t in targets if t in graph] for node, targets in graph.items()}
    for group in _strongly_connected(edges):
        if len(group) > 1 or group[0] in edges[group[0]]:
            names = ", ".join(f"'{n}'" for n in sorted(group))
            who = f"Step {names} links back to itself, a loop" if len(group) == 1 else f"Steps {names} form a loop"
            errors.append(f"{who} made only of branch and delay steps, which can never end; "
                          "put an action or wait step in the loop, or remove the link back")


def _strongly_connected(edges: Dict[str, List[str]]) -> List[List[str]]:
    """Tarjan's algorithm, iterative so a long chain of steps cannot hit the recursion limit."""
    index, low, on_stack, stack, result = {}, {}, set(), [], []
    counter = 0
    for root in edges:
        if root in index:
            continue
        work = [(root, iter(edges[root]))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, children = work[-1]
            advanced = False
            for child in children:
                if child not in index:
                    index[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(edges[child])))
                    advanced = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                group = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    group.append(member)
                    if member == node:
                        break
                result.append(group)
    return result
