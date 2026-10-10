"""Checks run when a workflow definition is saved, so mistakes show up then and not as a failed run."""
import copy
import json
import pathlib
import re

import pytest

import src.shared.connectors.definitions  # noqa: F401  (registers the real connectors)
from src.engine.steps import OPERATORS, evaluate_condition
from src.engine.validation import validate_definition
from src.shared.connectors.registry import registry

ROOT = pathlib.Path(__file__).resolve().parents[2]

GOOD = {
    "trigger": {"connector_id": "http", "trigger_id": "http_request_received", "config": {}},
    "start_at": "check",
    "steps": {
        "check": {"type": "branch", "condition": {"field": "order.quantity", "operator": "gte", "value": 100},
                  "on_true": "big", "on_false": "end"},
        "big": {"type": "action", "connector_id": "internal", "action_id": "log", "config": {"message": "hi"},
                "next": "pause", "retry": {"max_attempts": 3, "delay_seconds": 5}},
        "pause": {"type": "delay", "duration_seconds": 30, "next": "ask"},
        "ask": {"type": "wait_for_event", "event_name": "approved", "timeout_seconds": 3600, "next": "end"},
    },
}


def check(mutate=None, **top):
    definition = copy.deepcopy(GOOD)
    definition.update(top)
    if mutate:
        mutate(definition)
    return validate_definition(definition, registry)


def step(definition, name):
    return definition["steps"][name]


def mentions(errors, *words):
    return any(all(w.lower() in e.lower() for w in words) for e in errors)


class TestAValidDefinition:
    def test_has_no_problems(self):
        assert check() == []

    def test_a_trigger_is_optional(self):
        assert check(lambda d: d.pop("trigger")) == []

    def test_the_seeded_workflow_is_valid(self):
        init_sql = (ROOT / "infrastructure" / "postgres" / "init.sql").read_text(encoding="utf-8")
        body = re.search(r"VALUES \(wf_id, 1, '(\{.*?\})'\);", init_sql, re.S).group(1)
        assert validate_definition(json.loads(body), registry) == []


class TestShape:
    @pytest.mark.parametrize("definition", [None, [], "x", 3])
    def test_the_definition_must_be_an_object(self, definition):
        assert validate_definition(definition, registry) == ["The workflow definition must be a JSON object"]

    @pytest.mark.parametrize("steps", [None, {}, [], "x"])
    def test_there_must_be_at_least_one_step(self, steps):
        assert mentions(check(steps=steps), "steps")

    def test_a_step_must_be_an_object(self):
        assert mentions(check(lambda d: d["steps"].update(big="nope")), "'big'", "object")

    def test_start_at_is_required(self):
        assert mentions(check(lambda d: d.pop("start_at")), "start_at", "required")

    def test_start_at_must_name_a_step(self):
        assert mentions(check(start_at="nowhere"), "start_at", "'nowhere'", "not")

    def test_start_at_cannot_be_end(self):
        assert mentions(check(start_at="end"), "start_at", "end")

    def test_end_is_a_reserved_step_name(self):
        def rename(d):
            d["steps"]["end"] = d["steps"].pop("pause")
            d["steps"]["big"]["next"] = "end"
        assert mentions(check(rename), "'end'", "reserved")

    def test_a_step_name_longer_than_the_database_column_is_refused(self):
        def rename(d):
            d["steps"]["x" * 101] = d["steps"].pop("pause")
            d["steps"]["big"]["next"] = "x" * 101
        assert mentions(check(rename), "100")

    def test_every_problem_is_reported_not_just_the_first(self):
        def break_it(d):
            d["steps"]["big"]["next"] = "missing_one"
            d["steps"]["pause"]["next"] = "missing_two"
        errors = check(break_it)
        assert mentions(errors, "missing_one") and mentions(errors, "missing_two")


class TestLinks:
    @pytest.mark.parametrize("name,field", [("big", "next"), ("pause", "next"), ("ask", "next"),
                                            ("check", "on_true"), ("check", "on_false")])
    def test_a_link_to_a_step_that_does_not_exist_is_reported(self, name, field):
        errors = check(lambda d: step(d, name).update({field: "ghost"}))
        assert mentions(errors, f"'{name}'", field, "'ghost'")

    @pytest.mark.parametrize("name,field", [("big", "next"), ("pause", "next"), ("ask", "next"),
                                            ("check", "on_true"), ("check", "on_false")])
    def test_a_missing_link_is_reported_and_end_is_how_to_finish(self, name, field):
        errors = check(lambda d: step(d, name).pop(field))
        assert mentions(errors, f"'{name}'", field, "required", "end")

    def test_a_link_must_be_text(self):
        assert mentions(check(lambda d: step(d, "big").update(next=5)), "'big'", "next")

    def test_end_is_always_a_valid_target(self):
        assert check(lambda d: step(d, "big").update(next="end")) == []


class TestActionSteps:
    def test_an_action_needs_an_action_id(self):
        assert mentions(check(lambda d: step(d, "big").pop("action_id")), "'big'", "action_id", "required")

    def test_an_action_needs_a_connector_id(self):
        assert mentions(check(lambda d: step(d, "big").update(connector_id="")), "'big'", "connector_id", "required")

    def test_an_unknown_connector_is_reported(self):
        assert mentions(check(lambda d: step(d, "big").update(connector_id="nonesuch")), "'big'", "connector_id", "'nonesuch'")

    def test_an_unknown_action_is_reported(self):
        assert mentions(check(lambda d: step(d, "big").update(action_id="nonesuch")), "unknown action_id 'nonesuch'")

    def test_an_action_that_belongs_to_another_connector_is_reported(self):
        errors = check(lambda d: step(d, "big").update(connector_id="slack", action_id="log"))
        assert mentions(errors, "'big'", "'log'", "belongs to", "'internal'", "'slack'")

    @pytest.mark.parametrize("name", ["branch", "delay", "wait_for_event"])
    def test_flow_control_actions_are_step_types_not_actions(self, name):
        errors = check(lambda d: step(d, "big").update(connector_id="flow_control", action_id=name))
        assert mentions(errors, "'big'", f"'{name}'", "step type")
        assert len(errors) == 1

    def test_config_must_be_an_object(self):
        assert mentions(check(lambda d: step(d, "big").update(config=["x"])), "'big'", "config", "object")

    def test_connection_id_must_be_text(self):
        assert mentions(check(lambda d: step(d, "big").update(connection_id=12)), "'big'", "connection_id")

    def test_a_missing_config_is_fine(self):
        assert check(lambda d: step(d, "big").pop("config")) == []

    def test_the_removed_python_step_is_rejected(self):
        errors = check(lambda d: step(d, "big").update(connector_id="python", action_id="python_execute"))
        assert errors, "python_execute must stay unavailable"


class TestRetry:
    @pytest.mark.parametrize("retry", [{"max_attempts": 0}, {"max_attempts": -2}, {"max_attempts": "3"},
                                       {"max_attempts": True}, {"max_attempts": 2.5}])
    def test_max_attempts_must_be_a_whole_number_of_at_least_one(self, retry):
        assert mentions(check(lambda d: step(d, "big").update(retry=retry)), "'big'", "max_attempts")

    @pytest.mark.parametrize("retry", [{"delay_seconds": -1}, {"delay_seconds": "5"}, {"delay_seconds": False}])
    def test_delay_seconds_must_be_zero_or_more(self, retry):
        assert mentions(check(lambda d: step(d, "big").update(retry=retry)), "'big'", "delay_seconds")

    def test_retry_must_be_an_object(self):
        assert mentions(check(lambda d: step(d, "big").update(retry="often")), "'big'", "retry", "object")

    def test_a_retry_with_defaults_is_fine(self):
        assert check(lambda d: step(d, "big").update(retry={})) == []


class TestBranchSteps:
    def test_a_condition_is_required(self):
        assert mentions(check(lambda d: step(d, "check").pop("condition")), "'check'", "condition", "required")

    def test_the_condition_needs_a_field(self):
        errors = check(lambda d: step(d, "check")["condition"].update(field=" "))
        assert mentions(errors, "'check'", "field", "required")

    def test_an_unknown_operator_is_reported_with_the_valid_ones(self):
        errors = check(lambda d: step(d, "check")["condition"].update(operator="roughly"))
        assert mentions(errors, "'check'", "operator", "'roughly'", "gte")

    def test_a_missing_operator_means_eq_as_it_does_in_the_engine(self):
        assert check(lambda d: step(d, "check")["condition"].pop("operator")) == []

    def test_every_operator_accepted_here_is_understood_by_the_engine(self):
        cases = {"eq": (1, 1), "neq": (1, 2), "gt": (2, 1), "gte": (1, 1), "lt": (1, 2), "lte": (1, 1),
                 "contains": ("abc", "b"), "exists": (1, None)}
        assert set(cases) == set(OPERATORS)
        for operator, (actual, expected) in cases.items():
            condition = {"field": "x", "operator": operator, "value": expected}
            assert evaluate_condition({"x": actual}, condition) is True, operator


class TestDelayAndWaitSteps:
    @pytest.mark.parametrize("value", [-1, "30", True, None])
    def test_duration_must_be_zero_or_more_seconds(self, value):
        assert mentions(check(lambda d: step(d, "pause").update(duration_seconds=value)), "'pause'", "duration_seconds")

    def test_a_duration_of_zero_is_fine(self):
        assert check(lambda d: step(d, "pause").update(duration_seconds=0)) == []

    @pytest.mark.parametrize("value", [0, -5, "soon", True])
    def test_a_wait_timeout_must_be_more_than_zero_seconds(self, value):
        assert mentions(check(lambda d: step(d, "ask").update(timeout_seconds=value)), "'ask'", "timeout_seconds")

    def test_a_wait_may_have_no_timeout(self):
        assert check(lambda d: step(d, "ask").pop("timeout_seconds")) == []

    def test_the_event_name_is_not_required_because_the_engine_ignores_it(self):
        assert check(lambda d: step(d, "ask").update(event_name="")) == []


class TestStepTypes:
    def test_an_unknown_type_is_reported(self):
        errors = check(lambda d: step(d, "big").update(type="loop"))
        assert mentions(errors, "'big'", "unknown type", "'loop'", "wait_for_event")

    def test_a_step_with_a_duration_is_a_delay_whatever_its_type_says(self):
        def make_delay(d):
            d["steps"]["big"] = {"type": "action", "duration_seconds": 5, "next": "end"}
        assert check(make_delay) == []


class TestLoops:
    def test_a_loop_made_only_of_branch_and_delay_steps_is_reported(self):
        def loop(d):
            d["steps"]["pause"]["next"] = "check"
            d["steps"]["check"]["on_true"] = "pause"
        errors = check(loop)
        assert mentions(errors, "loop", "check", "pause", "action")

    def test_a_branch_pointing_at_itself_is_reported(self):
        errors = check(lambda d: step(d, "check").update(on_true="check"))
        assert mentions(errors, "Step 'check' links back to itself", "loop")

    def test_a_loop_through_an_action_is_allowed_because_polling_is_a_real_use(self):
        def poll(d):
            d["steps"]["ask"]["next"] = "check"
        assert check(poll) == []

    def test_a_loop_is_reported_once(self):
        def loop(d):
            d["steps"]["pause"]["next"] = "check"
            d["steps"]["check"]["on_true"] = "pause"
        assert len([e for e in check(loop) if "loop" in e.lower()]) == 1


class TestTrigger:
    def test_the_trigger_must_be_an_object(self):
        assert mentions(check(trigger="http"), "trigger", "object")

    def test_an_unknown_trigger_connector_is_reported(self):
        trigger = {"connector_id": "nonesuch", "trigger_id": "x", "config": {}}
        assert mentions(check(trigger=trigger), "trigger", "connector_id", "'nonesuch'")

    def test_a_trigger_the_connector_does_not_have_is_reported(self):
        trigger = {"connector_id": "github", "trigger_id": "slack_message_received", "config": {}}
        assert mentions(check(trigger=trigger), "trigger", "'slack_message_received'", "github")

    def test_a_trigger_needs_both_ids(self):
        assert mentions(check(trigger={"config": {}}), "trigger", "connector_id", "required")

    def test_trigger_config_must_be_an_object(self):
        trigger = {"connector_id": "http", "trigger_id": "http_request_received", "config": "x"}
        assert mentions(check(trigger=trigger), "trigger", "config", "object")


class TestInputs:
    def test_inputs_must_be_a_list_of_named_objects(self):
        assert mentions(check(inputs="x"), "inputs", "list")
        assert mentions(check(inputs=["x"]), "inputs", "object")
        assert mentions(check(inputs=[{"type": "string"}]), "inputs", "name")

    def test_input_names_must_be_unique(self):
        assert mentions(check(inputs=[{"name": "a"}, {"name": "a"}]), "inputs", "'a'", "twice")

    def test_valid_inputs_pass(self):
        assert check(inputs=[{"name": "order_id", "type": "string", "required": True}]) == []


def test_every_example_definition_in_the_docs_is_valid():
    """The JSON examples in README.md and docs/architecture.md are what people copy."""
    problems = []
    for path in [ROOT / "README.md", ROOT / "docs" / "architecture.md"]:
        for block in re.findall(r"```json\n(.*?)```", path.read_text(encoding="utf-8"), re.S):
            try:
                definition = json.loads(block)
            except ValueError:
                continue
            if isinstance(definition, dict) and "steps" in definition:
                problems += [f"{path.name}: {e}" for e in validate_definition(definition, registry)]
    assert problems == []
