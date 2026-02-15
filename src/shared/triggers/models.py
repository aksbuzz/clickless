from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class TriggerEvent:
    """A standardized event extracted from an external webhook payload."""
    connector_id: str
    trigger_id: str
    source_event_type: str
    data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TriggerValidationResult:
    """Result of webhook signature/authenticity validation."""
    is_valid: bool
    error_message: Optional[str] = None
    challenge_response: Optional[str] = None
