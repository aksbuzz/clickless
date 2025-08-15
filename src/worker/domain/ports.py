from abc import ABC, abstractmethod
from typing import Optional

from src.worker.domain.models import ActionResult


class WorkflowStatePort(ABC):
  @abstractmethod
  def load_state(self, instance_id: str):
    pass

  @abstractmethod
  def save_result(self, instance_id: str, action: str, result: ActionResult):
    pass

  @abstractmethod
  def send_event(self, event_type: str, instance_id: str, step: str):
    pass


class ActionHandlerPort(ABC):
  @abstractmethod
  def execute(self, instance_id: str, data: dict, **kwargs) -> ActionResult:
    pass


class ActionRegistryPort(ABC):
  @abstractmethod
  def get_handler(self, action_name: str) -> Optional[ActionHandlerPort]:
    pass
