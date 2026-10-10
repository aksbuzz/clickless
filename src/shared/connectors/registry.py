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


# Module-level singleton
registry = ConnectorRegistry()
