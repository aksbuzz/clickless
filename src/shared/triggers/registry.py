from typing import Dict, Optional

from src.shared.triggers.ports import TriggerHandlerPort


class TriggerHandlerRegistry:
    """Registry mapping connector_id to TriggerHandlerPort implementation."""

    def __init__(self):
        self._handlers: Dict[str, TriggerHandlerPort] = {}

    def register(self, connector_id: str, handler: TriggerHandlerPort) -> None:
        self._handlers[connector_id] = handler

    def get_handler(self, connector_id: str) -> Optional[TriggerHandlerPort]:
        return self._handlers.get(connector_id)
