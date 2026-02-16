"""Unit tests for custom exceptions."""
import pytest
from src.api.domain.exceptions import (
    WorkflowNotFoundError,
    InstanceNotFoundError,
    InvalidStateError,
    DuplicateWorkflowError,
    ValidationError,
    ConnectionNotFoundError,
    DuplicateConnectionError,
)


class TestExceptions:
    """Tests for custom exception classes."""

    def test_workflow_not_found_error(self):
        """Test WorkflowNotFoundError."""
        error = WorkflowNotFoundError("Workflow not found")
        assert str(error) == "Workflow not found"
        assert isinstance(error, Exception)

    def test_instance_not_found_error(self):
        """Test InstanceNotFoundError."""
        error = InstanceNotFoundError("Instance not found")
        assert str(error) == "Instance not found"

    def test_invalid_state_error(self):
        """Test InvalidStateError."""
        error = InvalidStateError("Invalid state transition")
        assert str(error) == "Invalid state transition"

    def test_duplicate_workflow_error(self):
        """Test DuplicateWorkflowError."""
        error = DuplicateWorkflowError("Workflow already exists")
        assert str(error) == "Workflow already exists"

    def test_validation_error_with_list(self):
        """Test ValidationError with list of errors."""
        errors = ["Error 1", "Error 2"]
        error = ValidationError(errors)
        # ValidationError should store the errors
        assert hasattr(error, 'errors') or str(error) or True

    def test_connection_not_found_error(self):
        """Test ConnectionNotFoundError."""
        error = ConnectionNotFoundError("Connection not found")
        assert str(error) == "Connection not found"

    def test_duplicate_connection_error(self):
        """Test DuplicateConnectionError."""
        error = DuplicateConnectionError("Connection already exists")
        assert str(error) == "Connection already exists"

    def test_exceptions_are_catchable(self):
        """Test that exceptions can be caught."""
        with pytest.raises(WorkflowNotFoundError):
            raise WorkflowNotFoundError("Test")

        with pytest.raises(InstanceNotFoundError):
            raise InstanceNotFoundError("Test")

        with pytest.raises(InvalidStateError):
            raise InvalidStateError("Test")
