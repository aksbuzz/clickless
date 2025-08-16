from dataclasses import dataclass
from typing import Dict, Any, Optional

from src.orchestration.domain.models import EventType


@dataclass
class WorkflowEvent:
    instance_id: str
    event_type: EventType
    step_name: Optional[str] = None
    data: Optional[Dict[str, Any]] = None