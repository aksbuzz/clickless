from celery.exceptions import Reject
from structlog.stdlib import BoundLogger

from src.worker.domain.models import ActionResult
from src.worker.domain.ports import ActionRegistryPort, WorkflowStatePort


class WorkerService:
  def __init__(self, state_repo: WorkflowStatePort, registry: ActionRegistryPort, logger: BoundLogger):
    self.state_repo = state_repo
    self.registry = registry
    self.log = logger

  def execute_action(self, action: str, instance_id: str):
    self.log.info("Executing action", action=action)

    definition, data, history = self.state_repo.load_state(instance_id)
    if any(h.get("step") == action and h.get("status") == "succeeded" for h in history):
      self.log.warning("Action already completed; ignoring", action=action)
      return

    handler = self.registry.get_handler(action)
    if not handler:
      raise Reject(f"No handler for action: {action}", requeue=False)

    result: ActionResult = handler.execute(instance_id, data)

    self.state_repo.save_result(instance_id, action, result)
    event_type = "STEP_COMPLETE" if result.status == "succeeded" else "STEP_FAILED"
    self.state_repo.send_event(event_type, instance_id, action)
    self.log.info("Action finished", action=action, status=result.status)