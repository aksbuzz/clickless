from abc import ABC, abstractmethod
from typing import Optional, Tuple
from datetime import datetime

from src.orchestration.domain.models import WorkflowStatus, WorkflowInstance, WorkflowVersion, WorkflowStepExecution

class WorkflowRepositoryPort(ABC):
  @abstractmethod
  def find_instance(self, instance_id: str) -> Optional[Tuple[WorkflowInstance, WorkflowVersion]]:
    """Finds a workflow instance and its corresponding version definition"""
    pass

  @abstractmethod
  def save_instance(self, instance: WorkflowInstance) -> None:
    """Saves the state of a WorkflowInstance"""
    pass
  
  @abstractmethod
  def find_current_step_execution(self, instance_id: str, step_name: str) -> Optional[WorkflowStepExecution]:
    """Finds the most recent step execution for a given instance and step name"""
    pass
  
  @abstractmethod
  def add_step_execution(self, step_execution: WorkflowStepExecution) -> None:
    """Adds a new step execution record"""
    pass

  @abstractmethod
  def save_step_execution(self, step_execution: WorkflowStepExecution) -> None:
    """Saves the state of a WorkflowStepExecution"""
    pass
  
  @abstractmethod
  def schedule_message(self, destination: str, payload: dict, publish_at: Optional[datetime] = None, request_id: str = None) -> None:
    """Schedules a message in the outbox for later publishing."""
    pass


class UnitOfWorkPort(ABC):
  workflow: WorkflowRepositoryPort
  def __enter__(self) -> "UnitOfWorkPort": ...
  def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...
  def commit(self) -> None: ...
  def rollback(self) -> None: ...

class LockPort(ABC):
  @abstractmethod
  def acquire_lock(self, key: str, timeout: int) -> bool: ...
  
  @abstractmethod
  def release_lock(self, key: str) -> None: ...

