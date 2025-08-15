from typing import Optional, Dict

from src.relay.domain.ports import TaskRouterPort

class DictTaskRouter(TaskRouterPort):
  def __init__(self, mapping: Dict[str, str]):
    self.mapping = mapping

  def resolve_task_name(self, destination: str) -> Optional[str]:
    return self.mapping.get(destination)