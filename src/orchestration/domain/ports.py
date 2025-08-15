from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime

from src.orchestration.domain.models import WorkflowStatus, WorkflowInstance, WorkflowDefinition

class WorkflowRepositoryPort(ABC):
    @abstractmethod
    def get_instance_with_definition(self, instance_id: str) -> Optional[tuple[WorkflowInstance, WorkflowDefinition]]:
        pass
    
    @abstractmethod
    def update_instance_status(self, instance_id: str, status: WorkflowStatus) -> None:
        pass
    
    @abstractmethod
    def schedule_step(self, instance_id: str, step_name: str, attempts: int = 1, 
                     publish_at: Optional[datetime] = None) -> None:
        pass

class LockPort(ABC):
    @abstractmethod
    def acquire_lock(self, key: str, timeout: int) -> bool:
        pass
    
    @abstractmethod
    def release_lock(self, key: str) -> None:
        pass

class EventPublisherPort(ABC):
    @abstractmethod
    def publish_step_result(self, instance_id: str, step_name: str, success: bool) -> None:
        pass