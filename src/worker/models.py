from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional

from src.shared.event_types import EventType


class ActionStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"


STEP_COMPLETE_EVENT = EventType.STEP_COMPLETE.value
STEP_FAILED_EVENT = EventType.STEP_FAILED.value
STEP_COMPLETED_STATUS = "completed"


@dataclass
class ActionResult:
    status: ActionStatus
    updated_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
