"""Unit tests for the API service. The database seam (db_cursor) and the repository are mocked."""
import os
import pytest
from unittest.mock import Mock, MagicMock, patch

# Set environment variables before importing modules
os.environ.setdefault('DATABASE_URL', 'postgresql://user:pass@localhost/test')

from src.api.service import WorkflowManagementService
from src.api.errors import (
    WorkflowNotFoundError,
    InstanceNotFoundError,
    InvalidStateError,
    ValidationError,
    DuplicateWorkflowError,
)
from src.shared.connectors.registry import ConnectorRegistry
from src.shared.connectors.models import Connector, ActionDefinition


class TestWorkflowManagementService:
    """Tests for WorkflowManagementService with a mocked cursor and repository."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_repo = Mock()
        cursor_patch = patch("src.api.service.db_cursor")
        db_cursor = cursor_patch.start()
        db_cursor.return_value.__enter__.return_value = Mock()
        db_cursor.return_value.__exit__.return_value = False
        repo_patch = patch("src.api.service.WorkflowRepository", return_value=self.mock_repo)
        repo_patch.start()
        self._patches = [cursor_patch, repo_patch]

        # Setup connector registry
        self.registry = ConnectorRegistry()
        http_connector = Connector(
            id="http",
            name="HTTP",
            description="HTTP connector",
            actions=[
                ActionDefinition(
                    id="get_request",
                    name="GET Request",
                    description="Make GET request",
                    config_schema={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"}
                        }
                    }
                )
            ],
            triggers=[],
            connection_schema={}
        )
        self.registry.register(http_connector)

        self.service = WorkflowManagementService(self.registry)

    def teardown_method(self):
        for p in self._patches:
            p.stop()

    def test_create_workflow_success(self):
        """Test successfully creating a workflow."""
        definition = {
            "start_at": "fetch",
            "steps": {
                "fetch": {
                    "type": "action",
                    "connector_id": "http",
                    "action_id": "get_request",
                    "config": {"url": "https://api.example.com"},
                    "next": "end"
                }
            }
        }

        self.mock_repo.create_workflow.return_value = "wf-123"
        self.mock_repo.create_version.return_value = "v-456"

        result = self.service.create_workflow("test_workflow", definition)

        assert result["workflow_id"] == "wf-123"
        assert result["version_id"] == "v-456"
        assert result["version"] == 1

        self.mock_repo.create_workflow.assert_called_once_with("test_workflow")
        self.mock_repo.create_version.assert_called_once_with("wf-123", version=1, definition=definition)

    def test_create_workflow_validation_error(self):
        """Test creating workflow with invalid definition."""
        invalid_definition = {
            "start_at": "fetch",
            "steps": {
                "fetch": {
                    "type": "action",
                    "connector_id": "nonexistent",
                    "action_id": "action1",
                    "config": {},
                    "next": "end"
                }
            }
        }

        with pytest.raises(ValidationError):
            self.service.create_workflow("test", invalid_definition)

    def test_create_workflow_duplicate_name(self):
        """Test creating workflow with duplicate name."""
        definition = {
            "start_at": "fetch",
            "steps": {
                "fetch": {
                    "type": "action",
                    "connector_id": "http",
                    "action_id": "get_request",
                    "config": {"url": "https://api.example.com"},
                    "next": "end"
                }
            }
        }

        # Simulate unique constraint violation
        self.mock_repo.create_workflow.side_effect = Exception("UNIQUE constraint failed")

        with pytest.raises(DuplicateWorkflowError):
            self.service.create_workflow("existing", definition)

    def test_get_workflow_success(self):
        """Test getting an existing workflow."""
        workflow_data = {
            "id": "wf-123",
            "name": "test_workflow",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00"
        }
        version_data = {
            "id": "v-456",
            "version": 1,
            "definition": {"start_at": "step1"},
            "is_active": True
        }

        self.mock_repo.get_workflow.return_value = workflow_data
        self.mock_repo.get_active_version.return_value = version_data

        result = self.service.get_workflow("wf-123")

        assert result["id"] == "wf-123"
        assert result["name"] == "test_workflow"
        assert result["active_version"] == version_data

    def test_get_workflow_not_found(self):
        """Test getting a non-existent workflow."""
        self.mock_repo.get_workflow.return_value = None

        with pytest.raises(WorkflowNotFoundError):
            self.service.get_workflow("nonexistent")

    def test_list_workflows(self):
        """Test listing all workflows."""
        workflows = [
            {"id": "wf-1", "name": "workflow1"},
            {"id": "wf-2", "name": "workflow2"}
        ]
        self.mock_repo.list_workflows.return_value = workflows

        result = self.service.list_workflows()

        assert len(result) == 2
        assert result[0]["id"] == "wf-1"
        self.mock_repo.list_workflows.assert_called_once()

    @patch('src.api.service.structlog')
    @patch('src.api.service.runtime')
    def test_start_workflow_hands_the_start_to_the_engine(self, mock_runtime, mock_structlog):
        mock_structlog.contextvars.get_contextvars.return_value = {"request_id": "req-123"}
        mock_runtime.start_instance.return_value = "inst-789"

        result = self.service.start_workflow("test_workflow", {"input": "data"})

        assert result == {"message": "Workflow started", "instance_id": "inst-789"}
        _cursor, name, data = mock_runtime.start_instance.call_args.args[:3]
        assert (name, data) == ("test_workflow", {"input": "data"})
        assert mock_runtime.start_instance.call_args.args[3:] == ("req-123",) or             mock_runtime.start_instance.call_args.kwargs.get("request_id") == "req-123"

    @patch('src.api.service.runtime')
    def test_start_workflow_not_found(self, mock_runtime):
        mock_runtime.start_instance.side_effect = WorkflowNotFoundError("Workflow definition not found")

        with pytest.raises(WorkflowNotFoundError):
            self.service.start_workflow("nonexistent", {})

    @patch('src.api.service.runtime')
    def test_trigger_webhook_starts_the_active_version(self, mock_runtime):
        self.mock_repo.find_active_version_by_name.return_value = {
            "id": "v-1", "definition": {"trigger": {"trigger_id": "webhook_received"}, "start_at": "first"}}
        mock_runtime.start_instance_for_version.return_value = "inst-1"

        result = self.service.trigger_webhook("wf", {"a": 1})

        assert result == {"message": "Workflow triggered", "instance_id": "inst-1"}
        args = mock_runtime.start_instance_for_version.call_args.args
        assert args[1:4] == ("v-1", "first", {"a": 1})

    @patch('src.api.service.runtime')
    def test_trigger_webhook_refuses_a_workflow_with_another_trigger(self, mock_runtime):
        self.mock_repo.find_active_version_by_name.return_value = {
            "id": "v-1", "definition": {"trigger": {"trigger_id": "github_push_received"}, "start_at": "first"}}

        with pytest.raises(InvalidStateError):
            self.service.trigger_webhook("wf", {})
        mock_runtime.start_instance_for_version.assert_not_called()

    @patch('src.api.service.runtime')
    def test_trigger_webhook_unknown_workflow(self, mock_runtime):
        self.mock_repo.find_active_version_by_name.return_value = None

        with pytest.raises(WorkflowNotFoundError):
            self.service.trigger_webhook("nope", {})

    @patch('src.api.service.runtime')
    def test_external_trigger_starts_one_instance_per_matching_workflow(self, mock_runtime):
        self.mock_repo.find_active_versions_by_trigger.return_value = [
            {"id": "v-1", "workflow_name": "match", "definition": {"start_at": "a", "trigger": {"config": {"repo": "x"}}}},
            {"id": "v-2", "workflow_name": "other", "definition": {"start_at": "b", "trigger": {"config": {"repo": "y"}}}},
        ]
        mock_runtime.start_instance_for_version.return_value = "inst-1"
        handler = Mock()
        handler.matches_workflow_config.side_effect = lambda event, config: config.get("repo") == "x"
        event = Mock(connector_id="github", trigger_id="github_push_received", data={"k": 1})

        started = self.service.process_external_trigger(event, handler)

        assert started == [{"workflow_name": "match", "instance_id": "inst-1"}]
        assert mock_runtime.start_instance_for_version.call_count == 1

    def test_get_instance_success(self):
        instance_data = {"id": "inst-123", "status": "running", "current_step": "step1", "data": {"key": "value"}}
        self.mock_repo.get_instance.return_value = instance_data

        result = self.service.get_instance("inst-123")

        assert result["id"] == "inst-123"
        assert result["status"] == "running"

    def test_get_instance_not_found(self):
        self.mock_repo.get_instance.return_value = None

        with pytest.raises(InstanceNotFoundError):
            self.service.get_instance("nonexistent")

    @patch('src.api.service.runtime')
    def test_cancel_instance_is_done_by_the_engine(self, mock_runtime):
        result = self.service.cancel_instance("inst-123")

        assert result == {"message": "Workflow cancelled", "instance_id": "inst-123"}
        assert mock_runtime.cancel_instance.call_args.args[1] == "inst-123"

    @patch('src.api.service.runtime')
    def test_cancel_instance_passes_engine_errors_through(self, mock_runtime):
        mock_runtime.cancel_instance.side_effect = InvalidStateError("Cannot cancel instance with status 'completed'")

        with pytest.raises(InvalidStateError):
            self.service.cancel_instance("inst-123")

    def test_list_instances(self):
        instances = [{"id": "inst-1", "status": "running"}, {"id": "inst-2", "status": "pending"}]
        self.mock_repo.list_instances.return_value = instances

        result = self.service.list_instances(status="running", limit=10)

        assert len(result) == 2
        self.mock_repo.list_instances.assert_called_once_with("running", None, 10, 0)

    def test_list_connectors(self):
        result = self.service.list_connectors()

        assert len(result) > 0
        assert any(c["id"] == "http" for c in result)

    @patch('src.api.service.runtime')
    def test_send_event_resumes_the_waiting_step_through_the_engine(self, mock_runtime):
        mock_runtime.send_event.return_value = "wait_step"

        result = self.service.send_event("inst-123", {"approved": True})

        assert result == {"message": "Event received, workflow resuming", "instance_id": "inst-123", "step": "wait_step"}
        assert mock_runtime.send_event.call_args.args[1:] == ("inst-123", {"approved": True})

    @patch('src.api.service.runtime')
    def test_send_event_passes_engine_errors_through(self, mock_runtime):
        mock_runtime.send_event.side_effect = InvalidStateError("Instance is not waiting for an event")

        with pytest.raises(InvalidStateError):
            self.service.send_event("inst-123", {})

    def test_the_service_no_longer_has_a_recovery_sweeper(self):
        assert not hasattr(self.service, "recover_stuck_instances")
