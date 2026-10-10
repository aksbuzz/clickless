"""A failed step must fail its instance and carry the error text; it must never strand the instance."""
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.orchestration.application.orchestration_service import OrchestrationService
from src.orchestration.domain.events import WorkflowEvent
from src.orchestration.domain.models import (
    EventType, StepExecutionStatus, WorkflowInstance, WorkflowStatus, WorkflowStepExecution, WorkflowVersion,
)
from src.worker.models import ActionResult, ActionStatus
from src.worker.service import WorkerService


# ------------------------------------------------------------------ engine side

def failing_step_fixture():
    now = datetime.now(timezone.utc)
    uow = MagicMock()
    service = OrchestrationService(uow, MagicMock())
    instance = WorkflowInstance(id="i-1", workflow_version_id="v-1", status=WorkflowStatus.RUNNING,
                                current_step="probe", current_step_attempts=1, data={}, created_at=now)
    version = WorkflowVersion(id="v-1", definition={"steps": {"probe": {"type": "action"}}}, workflow_name="w")
    execution = WorkflowStepExecution(id="e-1", instance_id="i-1", step_name="probe",
                                      status=StepExecutionStatus.RUNNING, attempts=1, started_at=now)
    uow.workflow.find_current_step_execution.return_value = execution
    return service, instance, version, execution


def test_a_failure_event_without_details_still_fails_the_instance():
    service, instance, version, execution = failing_step_fixture()
    event = WorkflowEvent(instance_id="i-1", event_type=EventType.STEP_FAILED, step_name="probe", data=None)

    service._handle_step_failure(instance, version, event)

    assert instance.status == WorkflowStatus.FAILED
    assert execution.status == StepExecutionStatus.FAILED
    assert execution.error_details == "Unknown error"


def test_the_error_text_carried_by_the_event_is_recorded():
    service, instance, version, execution = failing_step_fixture()
    event = WorkflowEvent(instance_id="i-1", event_type=EventType.STEP_FAILED, step_name="probe",
                          data={"error": "Blocked outbound request: 'rabbitmq' resolves to a non-public address"})

    service._handle_step_failure(instance, version, event)

    assert instance.status == WorkflowStatus.FAILED
    assert execution.error_details == "Blocked outbound request: 'rabbitmq' resolves to a non-public address"


# ------------------------------------------------------------------ worker side

class ScriptedCursor:
    """Answers the worker's two lookups (existing step execution, instance row) and records every INSERT."""

    def __init__(self):
        self.answers = [None, {"id": "i-1", "data": {}}]
        self.inserts = []

    def execute(self, query, params=None):
        if query.lstrip().upper().startswith("INSERT"):
            self.inserts.append((query, params))

    def fetchone(self):
        return self.answers.pop(0)


def run_worker(result: ActionResult):
    cursor = ScriptedCursor()

    @contextmanager
    def fake_db_cursor():
        yield cursor

    handler = MagicMock()
    handler.execute.return_value = result
    from src.worker import service as worker_service
    original = worker_service.db_cursor
    worker_service.db_cursor = fake_db_cursor
    try:
        WorkerService({"act": handler}).execute_action("act", "i-1", step_name="probe")
    finally:
        worker_service.db_cursor = original
    (query, params), = cursor.inserts
    assert "outbox" in query
    return json.loads(params[1])   # params = (destination, payload json)


def test_worker_sends_the_error_message_with_a_failed_step():
    payload = run_worker(ActionResult(ActionStatus.FAILURE, {"a": 1}, error_message="Blocked outbound request: nope"))
    assert payload["type"] == EventType.STEP_FAILED.value
    assert payload["data"] == {"error": "Blocked outbound request: nope"}


def test_worker_gives_a_failed_step_a_default_error_when_the_handler_gave_none():
    payload = run_worker(ActionResult(ActionStatus.FAILURE, {}))
    assert payload["data"] == {"error": "Unknown error"}


def test_worker_still_sends_updated_data_with_a_completed_step():
    payload = run_worker(ActionResult(ActionStatus.SUCCESS, {"x": 1}))
    assert payload["type"] == EventType.STEP_COMPLETE.value
    assert payload["data"] == {"x": 1}
