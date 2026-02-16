"""Unit tests for domain models."""
import pytest
from datetime import datetime
from src.orchestration.domain.models import (
    WorkflowStatus,
    StepExecutionStatus,
    WorkflowVersion,
    WorkflowInstance,
    WorkflowStepExecution,
    RetryPolicy,
)


class TestWorkflowVersion:
    """Tests for WorkflowVersion domain model."""

    def test_get_start_step(self):
        """Test getting the start step from definition."""
        definition = {"start_at": "step1", "steps": {}}
        version = WorkflowVersion(id="v1", definition=definition)

        assert version.get_start_step() == "step1"

    def test_get_next_step(self):
        """Test getting the next step."""
        definition = {
            "start_at": "step1",
            "steps": {
                "step1": {"next": "step2"},
                "step2": {"next": "end"}
            }
        }
        version = WorkflowVersion(id="v1", definition=definition)

        assert version.get_next_step("step1") == "step2"
        assert version.get_next_step("step2") == "end"

    def test_get_next_step_missing(self):
        """Test getting next step for non-existent step."""
        definition = {"start_at": "step1", "steps": {}}
        version = WorkflowVersion(id="v1", definition=definition)

        assert version.get_next_step("nonexistent") is None

    def test_get_step_definition(self):
        """Test getting step definition."""
        step_def = {
            "type": "action",
            "connector_id": "http",
            "action_id": "get_request"
        }
        definition = {
            "start_at": "fetch",
            "steps": {"fetch": step_def}
        }
        version = WorkflowVersion(id="v1", definition=definition)

        result = version.get_step_definition("fetch")
        assert result == step_def

    def test_get_step_definition_missing(self):
        """Test getting definition for non-existent step."""
        definition = {"start_at": "step1", "steps": {}}
        version = WorkflowVersion(id="v1", definition=definition)

        assert version.get_step_definition("nonexistent") is None


class TestWorkflowInstance:
    """Tests for WorkflowInstance domain model."""

    def test_create_instance(self):
        """Test creating a workflow instance."""
        instance = WorkflowInstance(
            id="inst1",
            workflow_version_id="v1",
            status=WorkflowStatus.PENDING,
            data={"key": "value"}
        )

        assert instance.id == "inst1"
        assert instance.workflow_version_id == "v1"
        assert instance.status == WorkflowStatus.PENDING
        assert instance.data == {"key": "value"}
        assert instance.current_step is None
        assert instance.current_step_attempts == 0

    def test_instance_with_current_step(self):
        """Test instance with a current step."""
        instance = WorkflowInstance(
            id="inst1",
            workflow_version_id="v1",
            status=WorkflowStatus.RUNNING,
            current_step="step1",
            current_step_attempts=2
        )

        assert instance.current_step == "step1"
        assert instance.current_step_attempts == 2


class TestWorkflowStepExecution:
    """Tests for WorkflowStepExecution domain model."""

    def test_create_step_execution(self):
        """Test creating a step execution."""
        now = datetime.now()
        execution = WorkflowStepExecution(
            id="exec1",
            instance_id="inst1",
            step_name="step1",
            status=StepExecutionStatus.RUNNING,
            attempts=1,
            started_at=now,
            input_data={"input": "data"}
        )

        assert execution.id == "exec1"
        assert execution.instance_id == "inst1"
        assert execution.step_name == "step1"
        assert execution.status == StepExecutionStatus.RUNNING
        assert execution.attempts == 1
        assert execution.started_at == now
        assert execution.input_data == {"input": "data"}
        assert execution.completed_at is None

    def test_completed_step_execution(self):
        """Test a completed step execution."""
        started = datetime.now()
        completed = datetime.now()

        execution = WorkflowStepExecution(
            id="exec1",
            instance_id="inst1",
            step_name="step1",
            status=StepExecutionStatus.COMPLETED,
            attempts=1,
            started_at=started,
            completed_at=completed,
            output_data={"result": "success"}
        )

        assert execution.status == StepExecutionStatus.COMPLETED
        assert execution.completed_at == completed
        assert execution.output_data == {"result": "success"}

    def test_failed_step_execution(self):
        """Test a failed step execution."""
        execution = WorkflowStepExecution(
            id="exec1",
            instance_id="inst1",
            step_name="step1",
            status=StepExecutionStatus.FAILED,
            attempts=3,
            started_at=datetime.now(),
            error_details="Connection timeout"
        )

        assert execution.status == StepExecutionStatus.FAILED
        assert execution.error_details == "Connection timeout"


class TestRetryPolicy:
    """Tests for RetryPolicy domain model."""

    def test_default_retry_policy(self):
        """Test default retry policy values."""
        policy = RetryPolicy()

        assert policy.max_attempts == 1
        assert policy.delay_seconds == 5

    def test_custom_retry_policy(self):
        """Test custom retry policy values."""
        policy = RetryPolicy(max_attempts=3, delay_seconds=10)

        assert policy.max_attempts == 3
        assert policy.delay_seconds == 10

    def test_from_dict_full(self):
        """Test creating retry policy from dict with all values."""
        data = {"max_attempts": 5, "delay_seconds": 15}
        policy = RetryPolicy.from_dict(data)

        assert policy.max_attempts == 5
        assert policy.delay_seconds == 15

    def test_from_dict_partial(self):
        """Test creating retry policy from dict with missing values."""
        data = {"max_attempts": 3}
        policy = RetryPolicy.from_dict(data)

        assert policy.max_attempts == 3
        assert policy.delay_seconds == 5  # default

    def test_from_dict_empty(self):
        """Test creating retry policy from empty dict."""
        policy = RetryPolicy.from_dict({})

        assert policy.max_attempts == 1  # default
        assert policy.delay_seconds == 5  # default


class TestWorkflowStatus:
    """Tests for WorkflowStatus enum."""

    def test_status_values(self):
        """Test workflow status enum values."""
        assert WorkflowStatus.PENDING.value == "pending"
        assert WorkflowStatus.RUNNING.value == "running"
        assert WorkflowStatus.COMPLETED.value == "completed"
        assert WorkflowStatus.FAILED.value == "failed"
        assert WorkflowStatus.CANCELLED.value == "cancelled"


class TestStepExecutionStatus:
    """Tests for StepExecutionStatus enum."""

    def test_status_values(self):
        """Test step execution status enum values."""
        assert StepExecutionStatus.PENDING.value == "pending"
        assert StepExecutionStatus.RUNNING.value == "running"
        assert StepExecutionStatus.COMPLETED.value == "completed"
        assert StepExecutionStatus.FAILED.value == "failed"
