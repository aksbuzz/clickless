from abc import ABC, abstractmethod
from typing import Any, Dict, List

from src.shared.triggers.models import TriggerEvent, TriggerValidationResult


class TriggerHandlerPort(ABC):
    """Port for handling incoming webhooks from external services."""

    @abstractmethod
    def validate_webhook(self, headers: Dict[str, str], body: bytes, config: Dict[str, Any]) -> TriggerValidationResult:
        """Validate webhook request authenticity (signature verification)."""
        pass

    @abstractmethod
    def parse_events(self, headers: Dict[str, str], body: bytes) -> List[TriggerEvent]:
        """Parse webhook payload into zero or more TriggerEvents."""
        pass

    @abstractmethod
    def matches_workflow_config(self, event: TriggerEvent, workflow_trigger_config: Dict[str, Any]) -> bool:
        """Check if a TriggerEvent matches a workflow's trigger configuration."""
        pass
