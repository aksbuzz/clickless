from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum

from src.shared.event_types import EventType  # noqa: F401 — re-exported for backward compat

# --- Enums ---

class WorkflowStatus(Enum):
  PENDING = "pending"
  RUNNING = "running"
  COMPLETED = "completed"
  FAILED = "failed"
  CANCELLED = "cancelled"

class StepExecutionStatus(Enum):
  PENDING = "pending"
  RUNNING = "running"
  COMPLETED = "completed"
  FAILED = "failed"


# --- Domain Models ---

@dataclass
class WorkflowVersion:
  id: str
  definition: Dict[str, Any]

  def get_start_step(self) -> str:
    return self.definition.get("start_at")
  
  def get_next_step(self, current_step: str) -> Optional[str]:
    return self.definition.get("steps", {}).get(current_step, {}).get("next")
  
  def get_step_definition(self, step_name: str) -> Optional[Dict[str, Any]]:
    return self.definition.get("steps", {}).get(step_name)


@dataclass
class WorkflowInstance:
  id: str
  workflow_version_id: str
  status: WorkflowStatus
  current_step: Optional[str] = None
  current_step_attempts: int = 0
  data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowStepExecution:
  id: str
  instance_id: str
  step_name: str
  status: StepExecutionStatus
  attempts: int
  started_at: datetime
  completed_at: Optional[datetime] = None
  input_data: Optional[Dict[str, Any]] = None
  output_data: Optional[Dict[str, Any]] = None
  error_details: Optional[str] = None


@dataclass
class RetryPolicy:
  max_attempts: int = 1
  delay_seconds: int = 5
    
  @classmethod
  def from_dict(cls, data: dict):
    return cls(
      max_attempts=data.get("max_attempts", 1),
      delay_seconds=data.get("delay_seconds", 5)
    )