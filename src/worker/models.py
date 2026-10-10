from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional


class ActionStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass
class ActionResult:
    status: ActionStatus
    updated_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
