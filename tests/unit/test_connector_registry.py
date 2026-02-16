"""Unit tests for connector registry."""
import pytest
from src.shared.connectors.models import Connector, ActionDefinition, TriggerDefinition
from src.shared.connectors.registry import ConnectorRegistry


class TestConnectorRegistry:
    """Tests for ConnectorRegistry."""

    def setup_method(self):
        """Set up test fixtures."""
        self.registry = ConnectorRegistry()

    def test_register_connector(self):
        """Test registering a connector."""
        connector = Connector(
            id="test",
            name="Test Connector",
            description="Test description",
            actions=[
                ActionDefinition(
                    id="test_action",
                    name="Test Action",
                    description="Test action description",
                    config_schema={"type": "object", "properties": {}}
                )
            ],
            triggers=[],
            connection_schema={"type": "object", "properties": {}}
        )

        self.registry.register(connector)

        result = self.registry.get_connector("test")
        assert result is not None
        assert result.id == "test"
        assert result.name == "Test Connector"

    def test_get_connector_not_found(self):
        """Test getting a non-existent connector."""
        result = self.registry.get_connector("nonexistent")
        assert result is None

    def test_list_connectors(self):
        """Test listing all connectors."""
        connector1 = Connector(
            id="test1",
            name="Test 1",
            description="Description 1",
            actions=[],
            triggers=[],
            connection_schema={}
        )
        connector2 = Connector(
            id="test2",
            name="Test 2",
            description="Description 2",
            actions=[],
            triggers=[],
            connection_schema={}
        )

        self.registry.register(connector1)
        self.registry.register(connector2)

        connectors = self.registry.list_connectors()
        assert len(connectors) >= 2
        ids = [c.id for c in connectors]
        assert "test1" in ids
        assert "test2" in ids

    def test_validate_definition_valid(self):
        """Test validating a valid workflow definition."""
        connector = Connector(
            id="http",
            name="HTTP",
            description="HTTP connector",
            actions=[
                ActionDefinition(
                    id="get_request",
                    name="GET Request",
                    description="Make a GET request",
                    config_schema={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"}
                        },
                        "required": ["url"]
                    }
                )
            ],
            triggers=[],
            connection_schema={}
        )

        self.registry.register(connector)

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

        errors = self.registry.validate_definition(definition)
        assert errors == []

    def test_validate_definition_missing_action(self):
        """Test validating definition with missing action."""
        connector = Connector(
            id="test",
            name="Test",
            description="Test",
            actions=[
                ActionDefinition(
                    id="action1",
                    name="Action 1",
                    description="Action 1",
                    config_schema={"type": "object", "properties": {}}
                )
            ],
            triggers=[],
            connection_schema={}
        )

        self.registry.register(connector)

        definition = {
            "start_at": "step1",
            "steps": {
                "step1": {
                    "type": "action",
                    "connector_id": "test",
                    "action_id": "nonexistent_action",
                    "config": {},
                    "next": "end"
                }
            }
        }

        errors = self.registry.validate_definition(definition)
        assert len(errors) > 0
        assert any("unknown action" in err.lower() for err in errors)

class TestConnectorModel:
    """Tests for Connector model."""

    def test_create_connector(self):
        """Test creating a connector."""
        connector = Connector(
            id="http",
            name="HTTP",
            description="HTTP connector",
            actions=[],
            triggers=[],
            connection_schema={"type": "object"}
        )

        assert connector.id == "http"
        assert connector.name == "HTTP"
        assert connector.description == "HTTP connector"
        assert connector.actions == []
        assert connector.triggers == []

    def test_connector_with_actions(self):
        """Test connector with actions."""
        action = ActionDefinition(
            id="get",
            name="GET Request",
            description="Make GET request",
            config_schema={"type": "object"}
        )

        connector = Connector(
            id="http",
            name="HTTP",
            description="HTTP",
            actions=[action],
            triggers=[],
            connection_schema={}
        )

        assert len(connector.actions) == 1
        assert connector.actions[0].id == "get"

    def test_connector_with_triggers(self):
        """Test connector with triggers."""
        trigger = TriggerDefinition(
            id="webhook",
            name="Webhook",
            description="Receive webhook",
            config_schema={"type": "object"}
        )

        connector = Connector(
            id="webhook",
            name="Webhook",
            description="Webhook",
            actions=[],
            triggers=[trigger],
            connection_schema={}
        )

        assert len(connector.triggers) == 1
        assert connector.triggers[0].id == "webhook"
