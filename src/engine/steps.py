"""Pure step logic: no database, no I/O."""
from typing import Any, Dict, Iterable, Tuple

from src.shared.connectors.template import resolve_config, resolve_field

STEP_KINDS = ("action", "branch", "delay", "wait_for_event")
OPERATORS = ("eq", "neq", "gt", "gte", "lt", "lte", "contains", "exists")   # what evaluate_condition understands


def evaluate_condition(data: dict, condition: dict) -> bool:
    """Evaluate a branch condition against instance data. Anything that cannot be evaluated is False."""
    actual = resolve_field(data, condition.get("field", ""))
    operator = condition.get("operator", "eq")
    expected = condition.get("value")
    try:
        if operator == "eq":
            return actual == expected
        if operator == "neq":
            return actual != expected
        if operator == "gt":
            return actual is not None and actual > expected
        if operator == "gte":
            return actual is not None and actual >= expected
        if operator == "lt":
            return actual is not None and actual < expected
        if operator == "lte":
            return actual is not None and actual <= expected
        if operator == "contains":
            return actual is not None and expected in actual
        if operator == "exists":
            return actual is not None
    except TypeError:
        return False
    return False


def step_kind(step: dict) -> str:
    """action, branch, delay or wait_for_event. A step with a duration is a delay whatever its type says."""
    kind = step.get("type", "action")
    if kind == "delay" or "duration_seconds" in step:
        return "delay"
    return kind if kind in STEP_KINDS else "action"


def retry_policy(step: dict) -> Tuple[int, int]:
    """(max_attempts, delay_seconds) for a step. One attempt unless the definition asks for more."""
    retry = step.get("retry") or {}
    try:
        max_attempts = int(retry.get("max_attempts", 1))
    except (TypeError, ValueError):
        max_attempts = 1
    try:
        delay_seconds = int(retry.get("delay_seconds", 5))
    except (TypeError, ValueError):
        delay_seconds = 5
    return max(1, max_attempts), max(0, delay_seconds)


def resolve_step_config(config: Dict[str, Any], data: Dict[str, Any], untemplated: Iterable[str] = ()) -> Dict[str, Any]:
    """Resolve {{field}} templates in a step's config against the instance data, in one place for every handler.

    Keys listed in `untemplated` are passed through exactly as written (for example a SQL query, which must
    never be built from data).
    """
    skip = set(untemplated)
    resolved = resolve_config({k: v for k, v in config.items() if k not in skip}, data)
    for key in skip:
        if key in config:
            resolved[key] = config[key]
    return resolved
