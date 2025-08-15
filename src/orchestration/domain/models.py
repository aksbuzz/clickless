from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from enum import Enum

class WorkflowStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"

class EventType(Enum):
    START_WORKFLOW = "START_WORKFLOW"
    STEP_COMPLETE = "STEP_COMPLETE"
    STEP_FAILED = "STEP_FAILED"


@dataclass
class WorkflowInstance:
    id: str
    definition_id: str
    status: WorkflowStatus
    current_step: Optional[str]
    attempts: int
    data: Dict[str, Any]
    history: List[Dict[str, Any]]
    
@dataclass
class WorkflowDefinition:
    id: str
    definition: Dict[str, Any]
    
    def get_start_step(self) -> str:
        return self.definition.get("start_at")
    
    def get_step_definition(self, step_name: str) -> Dict[str, Any]:
        return self.definition.get("steps", {}).get(step_name, {})
    
    def get_next_step(self, current_step: str) -> Optional[str]:
        step_def = self.get_step_definition(current_step)
        return step_def.get("next")

@dataclass
class RetryPolicy:
    max_attempts: int
    delay_seconds: int = 5
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional['RetryPolicy']:
        if not data:
            return None
        return cls(
            max_attempts=data.get("max_attempts", 1),
            delay_seconds=data.get("delay_seconds", 5)
        )