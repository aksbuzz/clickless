from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from src.shared.logging_config import log
from src.shared.constants import ORCHESTRATION_QUEUE, ACTIONS_QUEUE

from src.orchestration.domain.models import EventType, RetryPolicy, WorkflowVersion, WorkflowStatus, WorkflowInstance, WorkflowStepExecution, StepExecutionStatus
from src.orchestration.domain.events import WorkflowEvent
from src.orchestration.domain.ports import UnitOfWorkPort, LockPort


class OrchestrationService:
  LOCK_TIMEOUT = 30
  
  def __init__(self, uow: UnitOfWorkPort, lock_service: LockPort):
    self.uow = uow
    self.lock_service = lock_service

  def process_event(self, event: WorkflowEvent) -> None:
    lock_key = f"lock:instance:{event.instance_id}"
    
    if not self.lock_service.acquire_lock(lock_key, self.LOCK_TIMEOUT):
      raise RetryableError("Could not acquire lock")

    try:
      self._handle_event(event)
    finally:
      self.lock_service.release_lock(lock_key)


  def _handle_event(self, event: WorkflowEvent) -> None:
    with self.uow:
      result = self.uow.workflow.find_instance(event.instance_id)
      if not result:
        raise NonRetryableError("Instance not found")
      
      instance, version = result

      # Guard: ignore events for terminal instances
      if instance.status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED):
        log.warning("Ignoring event for terminal instance", instance_id=instance.id, status=instance.status.value)
        return

      if event.event_type == EventType.STEP_FAILED:
        self._handle_step_failure(instance, version, event)
      
      elif event.event_type == EventType.START_WORKFLOW:
        self._handle_workflow_start(instance, version)
      
      elif event.event_type == EventType.STEP_COMPLETE:
        self._handle_step_completion(instance, version, event)


  def _handle_step_failure(self, instance: WorkflowInstance, version: WorkflowVersion, event: WorkflowEvent) -> None:
    if instance.current_step != event.step_name:
      log.warning("Ignoring stale step failure event",
        expected_step=instance.current_step, received_step=event.step_name)
      return

    step_def = version.get_step_definition(event.step_name)
    retry_policy = RetryPolicy.from_dict(step_def.get("retry", {}))

    step_execution = self.uow.workflow.find_current_step_execution(instance.id, event.step_name)
    if not step_execution:
      log.error("Cannot process failure for a non-existent step execution.", step=event.step_name)
      return
    
    if instance.current_step_attempts < retry_policy.max_attempts:
      log.info("Scheduling retry", step=event.step_name, attempts=instance.current_step_attempts + 1)
      instance.current_step_attempts += 1
      self.uow.workflow.save_instance(instance)

      publish_time = datetime.now(timezone.utc) + timedelta(seconds=retry_policy.delay_seconds)
      action_id = step_def.get('action_id', event.step_name)
      config = step_def.get('config', {})
      payload = {
        "action": action_id,
        "step_name": event.step_name,
        "instance_id": instance.id,
        "config": config,
      }
      connection_id = step_def.get('connection_id')
      if connection_id:
        payload["connection_id"] = connection_id
      self.uow.workflow.schedule_message(ACTIONS_QUEUE, payload, publish_time)
    else:
      log.error("Step failed permanently", step=event.step_name)
      instance.status = WorkflowStatus.FAILED
      self.uow.workflow.save_instance(instance)
      
      step_execution.status = StepExecutionStatus.FAILED
      step_execution.completed_at = datetime.now(timezone.utc)
      step_execution.error_details = str(event.data.get("error", "Unknown error"))
      self.uow.workflow.save_step_execution(step_execution)


  def _handle_workflow_start(self, instance: WorkflowInstance, version: WorkflowVersion) -> None:
    if instance.status != WorkflowStatus.PENDING:
      log.warning("Workflow already started", instance_id=instance.id, status=instance.status.value)
      return
    
    start_step_name = version.get_start_step()
    self._transition_to_step(instance, version, start_step_name)


  def _handle_step_completion(self, instance: WorkflowInstance, version: WorkflowVersion, event: WorkflowEvent) -> None:
    if instance.current_step != event.step_name:
      log.warning("Ignoring stale step completion event",
        expected_step=instance.current_step, received_step=event.step_name)
      return

    self._complete_current_step(instance, event.step_name, event.data)
    
    next_step_name = version.get_next_step(instance.current_step)
    self._transition_to_step(instance, version, next_step_name)

  def _complete_current_step(self, instance: WorkflowInstance, step_name: str, result_data: Optional[dict]):
    step_execution = self.uow.workflow.find_current_step_execution(instance.id, step_name)
    if step_execution:
      step_execution.status = StepExecutionStatus.COMPLETED
      step_execution.completed_at = datetime.now(timezone.utc)
      step_execution.output_data = result_data
      self.uow.workflow.save_step_execution(step_execution)

    # Merge data into the main instance
    if result_data:
      instance.data.update(result_data)

  def _transition_to_step(self, instance: WorkflowInstance, version: WorkflowVersion, step_name: Optional[str]) -> None:
    if not step_name or step_name == "end":
      log.info("Workflow completed successfully", instance_id=instance.id)
      instance.status = WorkflowStatus.COMPLETED
      instance.current_step = None
      self.uow.workflow.save_instance(instance)
      return
    
    instance.status = WorkflowStatus.RUNNING
    instance.current_step = step_name
    instance.current_step_attempts = 1
    self.uow.workflow.save_instance(instance)

    # Create new step execution
    new_step_execution = WorkflowStepExecution(
      id=str(uuid.uuid4()),
      instance_id=instance.id,
      step_name=step_name,
      status=StepExecutionStatus.PENDING,
      attempts=1,
      started_at=datetime.now(timezone.utc),
      input_data=instance.data,
    )
    self.uow.workflow.add_step_execution(new_step_execution)

    step_def = version.get_step_definition(step_name)

    # Handle system steps
    if step_def.get('type') == 'delay' or 'duration_seconds' in step_def:
      self._handle_delay_step(instance.id, step_name, step_def)
      return

    if step_def.get('type') == 'branch':
      self._handle_branch_step(instance, version, step_name, step_def)
      return

    if step_def.get('type') == 'wait_for_event':
      self._handle_wait_step(instance, step_name, step_def)
      return

    # Dispatch action to worker
    action_id = step_def.get('action_id', step_name)
    config = step_def.get('config', {})
    payload = {
      "action": action_id,
      "step_name": step_name,
      "instance_id": instance.id,
      "config": config,
    }
    connection_id = step_def.get('connection_id')
    if connection_id:
      payload["connection_id"] = connection_id
    publish_time = datetime.now(timezone.utc)
    self.uow.workflow.schedule_message(ACTIONS_QUEUE, payload, publish_time)

  def _handle_delay_step(self, instance_id: str, step_name: str, step_def: dict) -> None:
    duration = int(step_def.get("duration_seconds", 60))
    resume_at = datetime.now(timezone.utc) + timedelta(seconds=duration)
    log.info("Pausing for delay", step=step_name, resume_at=resume_at.isoformat())

    step_execution = self.uow.workflow.find_current_step_execution(instance_id, step_name)
    if step_execution:
      step_execution.status = StepExecutionStatus.COMPLETED
      step_execution.completed_at = datetime.now(timezone.utc)
      self.uow.workflow.save_step_execution(step_execution)
    
    payload = {"type": EventType.STEP_COMPLETE.value, "instance_id": instance_id, "step_name": step_name}
    self.uow.workflow.schedule_message(ORCHESTRATION_QUEUE, payload, resume_at)


  def _handle_wait_step(self, instance: WorkflowInstance, step_name: str, step_def: dict) -> None:
    """Pause the workflow until an external event arrives via the API."""
    step_execution = self.uow.workflow.find_current_step_execution(instance.id, step_name)
    if step_execution:
      step_execution.status = StepExecutionStatus.RUNNING
      self.uow.workflow.save_step_execution(step_execution)

    # If a timeout is configured, schedule a STEP_FAILED as a safety net
    timeout_seconds = step_def.get('timeout_seconds')
    if timeout_seconds:
      timeout_at = datetime.now(timezone.utc) + timedelta(seconds=int(timeout_seconds))
      payload = {
        "type": EventType.STEP_FAILED.value,
        "instance_id": instance.id,
        "step_name": step_name,
        "data": {"error": f"Wait step '{step_name}' timed out after {timeout_seconds}s"},
      }
      self.uow.workflow.schedule_message(ORCHESTRATION_QUEUE, payload, timeout_at)
      log.info("Waiting for external event (with timeout)", step=step_name, timeout_seconds=timeout_seconds)
    else:
      log.info("Waiting for external event (no timeout)", step=step_name)

  def _handle_branch_step(self, instance: WorkflowInstance, version: WorkflowVersion, step_name: str, step_def: dict) -> None:
    condition = step_def.get('condition', {})
    result = self._evaluate_condition(instance.data, condition)

    next_step = step_def.get('on_true') if result else step_def.get('on_false')
    log.info("Branch evaluated", step=step_name, result=result, next_step=next_step)

    step_execution = self.uow.workflow.find_current_step_execution(instance.id, step_name)
    if step_execution:
      step_execution.status = StepExecutionStatus.COMPLETED
      step_execution.completed_at = datetime.now(timezone.utc)
      step_execution.output_data = {"branch_result": result, "next_step": next_step}
      self.uow.workflow.save_step_execution(step_execution)

    self._transition_to_step(instance, version, next_step)

  def _evaluate_condition(self, data: dict, condition: dict) -> bool:
    field_path = condition.get('field', '')
    operator = condition.get('operator', 'eq')
    expected = condition.get('value')

    actual = self._resolve_field(data, field_path)

    if operator == 'eq': return actual == expected
    if operator == 'neq': return actual != expected
    if operator == 'gt': return actual is not None and actual > expected
    if operator == 'gte': return actual is not None and actual >= expected
    if operator == 'lt': return actual is not None and actual < expected
    if operator == 'lte': return actual is not None and actual <= expected
    if operator == 'contains': return actual is not None and expected in actual
    if operator == 'exists': return actual is not None
    return False

  @staticmethod
  def _resolve_field(data: dict, field_path: str):
    """Resolve a dot-separated field path like 'invoice_details.amount'."""
    parts = field_path.split('.')
    current = data
    for part in parts:
      if isinstance(current, dict):
        current = current.get(part)
      else:
        return None
    return current


class RetryableError(Exception): pass
class NonRetryableError(Exception): pass
