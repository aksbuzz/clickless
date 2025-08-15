from typing import Dict, Optional

from src.worker.domain.ports import ActionRegistryPort, ActionHandlerPort

class DictActionRegistry(ActionRegistryPort):
  def __init__(self, handlers: Dict[str, ActionHandlerPort]):
    self.handlers = handlers

  def get_handler(self, action_name: str) -> Optional[ActionHandlerPort]:
    return self.handlers.get(action_name)