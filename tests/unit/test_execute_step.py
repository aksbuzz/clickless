"""execute_step turns every outcome, including every kind of failure, into a StepOutcome and never raises."""
import time

from src.engine.runtime import StepWork
from src.engine.worker import execute_step
from src.worker.models import ActionResult, ActionStatus
from src.worker.handlers.postgresql import PostgresQueryHandler


def work(config=None, data=None, step_def=None, pre_error=None):
    return StepWork(instance_id="i-1", step="s", step_def=step_def if step_def is not None else {"action_id": "act"}, execution_id="e-1", attempt=1,
                    data=data if data is not None else {"name": "Ada"}, config=config or {}, request_id=None,
                    workflow_name="w", started=time.monotonic(), pre_error=pre_error)


class Handler:
    def __init__(self, result=None, raises=None, mutate=None):
        self.result, self.raises, self.mutate, self.seen = result, raises, mutate, None

    def execute(self, instance_id, data, config=None, **kwargs):
        self.seen = {"data": data, "config": config}
        if self.mutate:
            data.update(self.mutate)
        if self.raises:
            raise self.raises
        return self.result or ActionResult(ActionStatus.SUCCESS, data)


def test_a_successful_handler_returns_its_data():
    outcome = execute_step(work(), {"act": Handler()})
    assert outcome.ok is True and outcome.data == {"name": "Ada"} and outcome.error is None


def test_a_failure_result_carries_the_handlers_message():
    handler = Handler(result=ActionResult(ActionStatus.FAILURE, {}, error_message="HTTP 500"))
    outcome = execute_step(work(), {"act": handler})
    assert outcome.ok is False and outcome.error == "HTTP 500"


def test_an_unknown_action_is_a_failure_with_a_reason():
    outcome = execute_step(work(step_def={"action_id": "nope"}), {})
    assert outcome.ok is False and "no handler registered for action 'nope'" in outcome.error


def test_the_step_name_is_the_action_id_when_none_is_given():
    outcome = execute_step(work(step_def={}), {"s": Handler()})
    assert outcome.ok is True


def test_an_exception_in_a_handler_is_a_failure_not_a_crash():
    outcome = execute_step(work(), {"act": Handler(raises=ValueError("bad input"))})
    assert outcome.ok is False and outcome.error == "ValueError: bad input"


def test_a_problem_found_before_running_skips_the_handler():
    handler = Handler()
    outcome = execute_step(work(pre_error="connection 'x' not found"), {"act": handler})
    assert outcome.ok is False and outcome.error == "connection 'x' not found"
    assert handler.seen is None


def test_templates_are_resolved_before_the_handler_sees_the_config():
    handler = Handler()
    execute_step(work(config={"greeting": "Hello {{name}}"}), {"act": handler})
    assert handler.seen["config"] == {"greeting": "Hello Ada"}


def test_a_handler_gets_a_copy_so_it_cannot_change_the_stored_data_in_place():
    step = work(data={"name": "Ada"})
    execute_step(step, {"act": Handler(mutate={"name": "Mallory"})})
    assert step.data == {"name": "Ada"}


def test_the_real_sql_handler_keeps_its_query_untemplated():
    handler = PostgresQueryHandler()
    step = work(config={"query": "SELECT '{{name}}'", "connection_string": "postgresql://{{name}}/d", "params": ["{{name}}"]},
                step_def={"action_id": "postgresql_query"})
    seen = {}

    def spy(instance_id, data, config=None, **kwargs):
        seen.update(config)
        return ActionResult(ActionStatus.SUCCESS, data)

    handler.execute = spy
    execute_step(step, {"postgresql_query": handler})
    assert seen == {"query": "SELECT '{{name}}'", "connection_string": "postgresql://{{name}}/d", "params": ["Ada"]}
