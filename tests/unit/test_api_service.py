"""Unit tests for API service with mocked dependencies."""
import os
import pytest
from unittest.mock import Mock, MagicMock, patch

# Set environment variables before importing modules
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379')
os.environ.setdefault('DATABASE_URL', 'postgresql://user:pass@localhost/test')
os.environ.setdefault('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')

from src.api.application.service import WorkflowManagementService
from src.api.domain.exceptions import (
    WorkflowNotFoundError,
    InstanceNotFoundError,
    InvalidStateError,
    ValidationError,
    DuplicateWorkflowError,
)
from src.shared.connectors.registry import ConnectorRegistry
from src.shared.connectors.models import Connector, ActionDefinition


class TestWorkflowManagementService:
    """Tests for WorkflowManagementService with mocked UoW."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_uow = Mock()
        self.mock_repo = Mock()
        self.mock_uow.repo = self.mock_repo
        self.mock_uow.__enter__ = Mock(return_value=self.mock_uow)
        self.mock_uow.__exit__ = Mock(return_value=False)

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

        self.service = WorkflowManagementService(self.mock_uow, self.registry)

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

    @patch('src.api.application.service.structlog')
    def test_start_workflow_success(self, mock_structlog):
        """Test starting a workflow."""
        mock_structlog.contextvars.get_contextvars.return_value = {"request_id": "req-123"}

        version_row = {
            "id": "v-456",
            "workflow_name": "test_workflow",
            "definition": {"start_at": "step1"}
        }

        self.mock_repo.find_active_version_by_name.return_value = version_row
        self.mock_repo.create_instance.return_value = "inst-789"

        result = self.service.start_workflow("test_workflow", {"input": "data"})

        assert result["instance_id"] == "inst-789"
        assert result["message"] == "Workflow started"

        self.mock_repo.create_instance.assert_called_once()
        self.mock_repo.schedule_outbox_message.assert_called_once()

    def test_start_workflow_not_found(self):
        """Test starting a non-existent workflow."""
        self.mock_repo.find_active_version_by_name.return_value = None

        with pytest.raises(WorkflowNotFoundError):
            self.service.start_workflow("nonexistent", {})

    def test_get_instance_success(self):
        """Test getting a workflow instance."""
        instance_data = {
            "id": "inst-123",
            "status": "running",
            "current_step": "step1",
            "data": {"key": "value"}
        }

        self.mock_repo.get_instance.return_value = instance_data

        result = self.service.get_instance("inst-123")

        assert result["id"] == "inst-123"
        assert result["status"] == "running"

    def test_get_instance_not_found(self):
        """Test getting a non-existent instance."""
        self.mock_repo.get_instance.return_value = None

        with pytest.raises(InstanceNotFoundError):
            self.service.get_instance("nonexistent")

    def test_cancel_instance_success(self):
        """Test canceling a running instance."""
        instance_data = {
            "id": "inst-123",
            "status": "running"
        }

        self.mock_repo.get_instance.return_value = instance_data

        result = self.service.cancel_instance("inst-123")

        assert result["message"] == "Workflow cancelled"
        self.mock_repo.update_instance_status.assert_called_once_with("inst-123", "cancelled")

    def test_cancel_instance_already_completed(self):
        """Test canceling a completed instance."""
        instance_data = {
            "id": "inst-123",
            "status": "completed"
        }

        self.mock_repo.get_instance.return_value = instance_data

        with pytest.raises(InvalidStateError):
            self.service.cancel_instance("inst-123")

    def test_list_instances(self):
        """Test listing instances with filters."""
        instances = [
            {"id": "inst-1", "status": "running"},
            {"id": "inst-2", "status": "pending"}
        ]

        self.mock_repo.list_instances.return_value = instances

        result = self.service.list_instances(status="running", limit=10)

        assert len(result) == 2
        self.mock_repo.list_instances.assert_called_once_with("running", None, 10, 0)

    def test_list_connectors(self):
        """Test listing available connectors."""
        result = self.service.list_connectors()

        assert len(result) > 0
        assert any(c["id"] == "http" for c in result)

    def test_send_event_success(self):
        """Test sending event to waiting workflow."""
        instance_data = {
            "id": "inst-123",
            "status": "running",
            "current_step": "wait_step",
            "definition": {
                "steps": {
                    "wait_step": {
                        "type": "wait_for_event",
                        "event_name": "approval"
                    }
                }
            }
        }

        self.mock_repo.get_instance_with_definition.return_value = instance_data

        result = self.service.send_event("inst-123", {"approved": True})

        assert result["message"] == "Event received, workflow resuming"
        self.mock_repo.schedule_outbox_message.assert_called_once()

    def test_send_event_instance_not_running(self):
        """Test sending event to non-running instance."""
        instance_data = {
            "id": "inst-123",
            "status": "completed",
            "current_step": "wait_step"
        }

        self.mock_repo.get_instance_with_definition.return_value = instance_data

        with pytest.raises(InvalidStateError):
            self.service.send_event("inst-123", {})

    def test_send_event_not_waiting_step(self):
        """Test sending event when step is not wait_for_event."""
        instance_data = {
            "id": "inst-123",
            "status": "running",
            "current_step": "action_step",
            "definition": {
                "steps": {
                    "action_step": {
                        "type": "action",
                        "connector_id": "http",
                        "action_id": "get"
                    }
                }
            }
        }

        self.mock_repo.get_instance_with_definition.return_value = instance_data

        with pytest.raises(InvalidStateError):
            self.service.send_event("inst-123", {})
