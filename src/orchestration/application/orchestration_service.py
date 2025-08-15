import structlog
from datetime import datetime, timedelta

from shared.loggin_config import setup_logging

from src.orchestration.domain.models import EventType, RetryPolicy, WorkflowDefinition, WorkflowStatus, WorkflowInstance
from src.orchestration.domain.events import WorkflowEvent
from src.orchestration.domain.ports import WorkflowRepositoryPort, LockPort, EventPublisherPort

setup_logging()
log = structlog.get_logger()


class OrchestrationService:
  LOCK_TIMEOUT = 30
  
  def __init__(
    self, 
    repository: WorkflowRepositoryPort,
    lock_service: LockPort,
    # event_publisher: EventPublisherPort
  ):
    self.repository = repository
    self.lock_service = lock_service
    # self.event_publisher = event_publisher

  def process_event(self, event: WorkflowEvent) -> None:
    lock_key = f"lock:instance:{event.instance_id}"
    
    if not self.lock_service.acquire_lock(lock_key, self.LOCK_TIMEOUT):
      raise RetryableError("Could not acquire lock")

    try:
      self._handle_event(event)
    finally:
      self.lock_service.release_lock(lock_key)


  def _handle_event(self, event: WorkflowEvent) -> None:
    result = self.repository.get_instance_with_definition(event.instance_id)
    if not result:
      raise NonRetryableError("Instance not found")
    
    instance, definition = result
    
    if event.event_type == EventType.STEP_FAILED:
      self._handle_step_failure(instance, definition, event.step_name)
    
    elif event.event_type == EventType.START_WORKFLOW:
      self._handle_workflow_start(instance, definition)
    
    elif event.event_type == EventType.STEP_COMPLETE:
      self._handle_step_completion(instance, definition)


  def _handle_step_failure(
    self, 
    instance: WorkflowInstance,
    definition: WorkflowDefinition, 
    step_name: str
  ) -> None:
    step_def = definition.get_step_definition(step_name)
    retry_policy = RetryPolicy.from_dict(step_def.get("retry", {}))
    
    if retry_policy and instance.attempts < retry_policy.max_attempts:
      log.info("Scheduling retry", step=step_name, attempts=instance.attempts)
      publish_time = datetime.utcnow() + timedelta(seconds=retry_policy.delay_seconds)
      self.repository.schedule_step(
        instance.id, 
        step_name,
        instance.attempts + 1, 
        publish_time
      )
    
    else:
      log.error("Step failed permanently", step=step_name)
      self.repository.update_instance_status(instance.id, WorkflowStatus.FAILED)


  def _handle_workflow_start(
    self, 
    instance: WorkflowInstance,
    definition: WorkflowDefinition
  ) -> None:
    if instance.status != WorkflowStatus.PENDING:
      log.warning("Workflow already started")
      return
    
    start_step = definition.get_start_step()
    self._transition_to_step(instance, definition, start_step)


  def _handle_step_completion(
    self, 
    instance: WorkflowInstance, 
    definition: WorkflowDefinition
  ) -> None:
    if self._is_duplicate_completion(instance):
      log.warning("Duplicate step completion ignored")
      return
    
    next_step = definition.get_next_step(instance.current_step)
    self._transition_to_step(instance, definition, next_step)

  def _transition_to_step(
    self,
    instance: WorkflowInstance,
    definition: WorkflowDefinition,
    step_name: str | None
  ) -> None:
    # Reached end
    if not step_name or step_name == "end":
      log.info("Workflow completed")
      self.repository.update_instance_status(instance.id, WorkflowStatus.SUCCEEDED)
      return
    
    step_def = definition.get_step_definition(step_name) or {}

    # System Step - DELAY 
    if step_def.get('type') == 'delay' or 'duration_seconds' in step_def:
      self._handle_delay_step(instance.id, step_name, step_def)
      return
    
    # TODO: System Step - IF / BRANCH

    self.repository.schedule_step(instance.id, step_name)

  def _handle_delay_step(self, instance_id: str, step_name: str, step_def: dict) -> None:
    duration = step_def.get("duration_seconds", 60)
    resume_at = datetime.utcnow() + timedelta(seconds=duration)

    log.info("Pausing for delay", step=step_name, resume_at=resume_at.isoformat())
    # TODO: implement this
    self.repository.schedule_orchestration_event()

  
  def _is_duplicate_completion(self, instance: WorkflowInstance) -> bool:
    if not instance.history:
      return False
    
    last_entry = instance.history[-1]
    return last_entry.get('step') == instance.current_step



class RetryableError(Exception):
    pass

class NonRetryableError(Exception):
    pass
