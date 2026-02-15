from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from src.worker.domain.models import ActionResult


class ActionHandlerPort(ABC):
  @abstractmethod
  def execute(self, instance_id: str, data: Dict[str, Any], config: Dict[str, Any] = None, **kwargs) -> ActionResult:
    """Executes the business logic for a specific workflow step."""
    pass


class ActionRegistryPort(ABC):
  @abstractmethod
  def get_handler(self, action_name: str) -> Optional["ActionHandlerPort"]: ...
