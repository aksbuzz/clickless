from celery.exceptions import Reject

from src.shared.logging_config import log

from src.worker.domain.models import ActionResult
from src.worker.domain.ports import ActionRegistryPort, UnitOfWorkPort


class WorkerService:
  def __init__(self, uow: UnitOfWorkPort, registry: ActionRegistryPort):
    self.uow = uow
    self.registry = registry

  def execute_action(self, action: str, instance_id: str, task_context=None):
    log.info("Executing action", action=action)

    with self.uow:
      _, data, history = self.uow.workflow.load_state(instance_id)
      if any(h.get("step") == action and h.get("status") == "succeeded" for h in history):
        log.warning("Action already completed; ignoring", action=action)
        return

      handler = self.registry.get_handler(action)
      if not handler:
        raise Reject(f"No handler for action: {action}", requeue=False)

      result: ActionResult = handler.execute(instance_id, data, task_context=task_context)

      # self.uow.workflow.save_result(instance_id, action, result)
      event_type = "STEP_COMPLETE" if result.status == "succeeded" else "STEP_FAILED"
      self.uow.workflow.send_event(
        event_type, 
        instance_id, 
        action,
        result.updated_data
      )
      
      log.info("Action finished", action=action, status=result.status)