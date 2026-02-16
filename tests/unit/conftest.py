"""Pytest configuration and fixtures for unit tests."""
import os
import pytest
from unittest.mock import Mock

# Set environment variables for all unit tests
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379')
os.environ.setdefault('DATABASE_URL', 'postgresql://user:pass@localhost/test')
os.environ.setdefault('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')


@pytest.fixture
def mock_repository():
    """Create a mock repository for testing."""
    repo = Mock()
    return repo


@pytest.fixture
def mock_unit_of_work(mock_repository):
    """Create a mock unit of work for testing."""
    uow = Mock()
    uow.repo = mock_repository
    uow.__enter__ = Mock(return_value=uow)
    uow.__exit__ = Mock(return_value=False)
    return uow


@pytest.fixture
def sample_workflow_definition():
    """Sample workflow definition for testing."""
    return {
        "description": "Sample workflow",
        "start_at": "step1",
        "steps": {
            "step1": {
                "type": "action",
                "connector_id": "http",
                "action_id": "get_request",
                "config": {"url": "https://api.example.com"},
                "next": "step2"
            },
            "step2": {
                "type": "action",
                "connector_id": "internal",
                "action_id": "log",
                "config": {"message": "Workflow completed"},
                "next": "end"
            }
        }
    }


@pytest.fixture
def sample_instance_data():
    """Sample instance data for testing."""
    return {
        "id": "inst-123",
        "workflow_version_id": "v-456",
        "status": "running",
        "current_step": "step1",
        "current_step_attempts": 0,
        "data": {
            "input": "test data",
            "user_id": "user-123"
        }
    }
