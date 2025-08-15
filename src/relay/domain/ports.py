from abc import ABC, abstractmethod
from typing import Iterable, List, Optional

from src.relay.domain.models import OutboxMessage


class OutboxRepositoryPort(ABC):
    @abstractmethod
    def fetch_due_messages(self, limit: int) -> List[OutboxMessage]:
        pass

    @abstractmethod
    def mark_processed(self, ids: Iterable[str]) -> None:
        pass


class TaskRouterPort(ABC):
    @abstractmethod
    def resolve_task_name(self, destination: str) -> Optional[str]:
        pass


class TaskPublisherPort(ABC):
    @abstractmethod
    def publish(self, task_name: str, queue: str, payload: str) -> None:
        pass
