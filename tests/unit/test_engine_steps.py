"""Pure step logic: conditions, step kinds, retry policy and central template resolution."""
import pytest

from src.engine.steps import evaluate_condition, resolve_step_config, retry_policy, step_kind


# ------------------------------------------------------------------ conditions

@pytest.mark.parametrize("condition,data,expected", [
    ({"field": "order.quantity", "operator": "gte", "value": 100}, {"order": {"quantity": 150}}, True),
    ({"field": "order.quantity", "operator": "gte", "value": 100}, {"order": {"quantity": 99}}, False),
    ({"field": "priority", "operator": "eq", "value": "high"}, {"priority": "high"}, True),
    ({"field": "priority", "operator": "neq", "value": "high"}, {"priority": "low"}, True),
    ({"field": "n", "operator": "gt", "value": 1}, {"n": 2}, True),
    ({"field": "n", "operator": "lt", "value": 1}, {"n": 0}, True),
    ({"field": "n", "operator": "lte", "value": 1}, {"n": 1}, True),
    ({"field": "tags", "operator": "contains", "value": "a"}, {"tags": ["a", "b"]}, True),
    ({"field": "name", "operator": "contains", "value": "ell"}, {"name": "hello"}, True),
    ({"field": "x", "operator": "exists"}, {"x": 0}, True),
    ({"field": "x", "operator": "exists"}, {}, False),
    ({"field": "a.b.c", "operator": "eq", "value": 1}, {"a": {"b": {"c": 1}}}, True),
])
def test_conditions(condition, data, expected):
    assert evaluate_condition(data, condition) is expected


@pytest.mark.parametrize("condition,data", [
    ({"field": "missing", "operator": "gt", "value": 1}, {}),            # absent fields never satisfy a comparison
    ({"field": "a.b", "operator": "eq", "value": 1}, {"a": "not a dict"}),
    ({"field": "x", "operator": "no_such_operator", "value": 1}, {"x": 1}),
    ({"field": "x", "operator": "contains", "value": "a"}, {}),
])
def test_conditions_that_cannot_be_evaluated_are_false(condition, data):
    assert evaluate_condition(data, condition) is False


def test_comparing_incompatible_types_is_false_instead_of_raising():
    assert evaluate_condition({"n": "text"}, {"field": "n", "operator": "gt", "value": 3}) is False


# ------------------------------------------------------------------ step kinds and retry policy

@pytest.mark.parametrize("step,kind", [
    ({"type": "action"}, "action"),
    ({}, "action"),                                             # type defaults to action
    ({"type": "branch"}, "branch"),
    ({"type": "delay", "duration_seconds": 5}, "delay"),
    ({"type": "wait_for_event"}, "wait_for_event"),
    ({"type": "action", "duration_seconds": 5}, "delay"),       # a duration makes any step a delay
])
def test_step_kind(step, kind):
    assert step_kind(step) == kind


def test_retry_policy_defaults_to_a_single_attempt():
    assert retry_policy({}) == (1, 5)
    assert retry_policy({"retry": None}) == (1, 5)


def test_retry_policy_reads_the_step_definition():
    assert retry_policy({"retry": {"max_attempts": 3, "delay_seconds": 2}}) == (3, 2)


@pytest.mark.parametrize("retry", [{"max_attempts": 0}, {"max_attempts": -4}, {"max_attempts": "x"}, {"delay_seconds": -1}])
def test_retry_policy_ignores_nonsense_values(retry):
    attempts, delay = retry_policy({"retry": retry})
    assert attempts >= 1 and delay >= 0


# ------------------------------------------------------------------ central template resolution

DATA = {"order": {"id": 7}, "state": "ready", "evil": "x'; DROP TABLE t; --"}


def test_templates_are_resolved_in_nested_values():
    config = {"message": "Order {{order.id}} is {{state}}", "headers": {"X-Order": "{{order.id}}"}, "tags": ["{{state}}", 3]}
    assert resolve_step_config(config, DATA) == {
        "message": "Order 7 is ready", "headers": {"X-Order": "7"}, "tags": ["ready", 3],
    }


def test_unknown_placeholders_are_left_as_written():
    assert resolve_step_config({"m": "{{nope}}"}, DATA) == {"m": "{{nope}}"}


def test_untemplated_keys_are_passed_through_exactly_as_written():
    config = {"query": "SELECT '{{evil}}'", "connection_string": "postgresql://{{state}}/d", "params": ["{{evil}}"]}
    resolved = resolve_step_config(config, DATA, untemplated=("query", "connection_string"))
    assert resolved["query"] == "SELECT '{{evil}}'"
    assert resolved["connection_string"] == "postgresql://{{state}}/d"
    assert resolved["params"] == ["x'; DROP TABLE t; --"]          # everything else is still resolved


def test_the_input_config_is_not_modified():
    config = {"m": "{{state}}"}
    resolve_step_config(config, DATA)
    assert config == {"m": "{{state}}"}
