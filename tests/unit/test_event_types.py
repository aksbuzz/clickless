"""Unit tests for event types."""
import pytest
from src.shared.event_types import EventType


class TestEventTypes:
    """Tests for EventType enum."""

    def test_event_type_values(self):
        """Test that event types have correct values."""
        assert EventType.START_WORKFLOW.value == "START_WORKFLOW"
        assert EventType.STEP_COMPLETE.value == "STEP_COMPLETE"
        assert EventType.STEP_FAILED.value == "STEP_FAILED"

    def test_event_type_from_value(self):
        """Test creating event type from string value."""
        event_type = EventType("START_WORKFLOW")
        assert event_type == EventType.START_WORKFLOW

    def test_all_event_types_unique(self):
        """Test that all event type values are unique."""
        values = [e.value for e in EventType]
        assert len(values) == len(set(values))
