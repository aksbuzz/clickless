from typing import Optional

from src.shared.connectors.models import Connector, ActionDefinition


class ConnectorRegistry:
    def __init__(self):
        self._connectors: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        self._connectors[connector.id] = connector

    def get_connector(self, connector_id: str) -> Optional[Connector]:
        return self._connectors.get(connector_id)

    def list_connectors(self) -> list[Connector]:
        return list(self._connectors.values())

    def get_action(self, action_id: str) -> Optional[ActionDefinition]:
        for connector in self._connectors.values():
            for action in connector.actions:
                if action.id == action_id:
                    return action
        return None

    def validate_definition(self, definition: dict) -> list[str]:
        """Validate that all action_ids in a workflow definition exist. Returns list of errors."""
        errors = []
        steps = definition.get("steps", {})
        for step_name, step_def in steps.items():
            step_type = step_def.get("type", "action")
            if step_type == "action":
                action_id = step_def.get("action_id")
                if action_id and not self.get_action(action_id):
                    errors.append(f"Step '{step_name}': unknown action_id '{action_id}'")
        return errors


# Module-level singleton
registry = ConnectorRegistry()
