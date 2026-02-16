import json

from celery.exceptions import Reject

from src.shared.logging_config import log
from src.shared.constants import ORCHESTRATION_QUEUE
from src.shared.db import get_connection, return_connection

from src.worker.domain.models import (
  ActionResult, ActionStatus,
  STEP_COMPLETE_EVENT, STEP_FAILED_EVENT, STEP_COMPLETED_STATUS,
)
from src.worker.domain.ports import ActionRegistryPort


class WorkerService:
  def __init__(self, registry: ActionRegistryPort):
    self.registry = registry

  def execute_action(self, action_name: str, instance_id: str, step_name: str = None, config: dict = None, connection_id: str = None, task_context=None):
    step_name = step_name or action_name
    config = config or {}
    log.info("Executing action", action=action_name, step=step_name, instance_id=instance_id)

    conn = get_connection()
    try:
      cur = conn.cursor()

      # Idempotency Check
      cur.execute(
        "SELECT id, status FROM workflow_step_executions "
        "WHERE instance_id = %s AND step_name = %s "
        "ORDER BY started_at DESC LIMIT 1",
        (instance_id, step_name)
      )
      step_exec = cur.fetchone()
      if step_exec and step_exec["status"] == STEP_COMPLETED_STATUS:
        log.warning("Action already completed; ignoring", action=action_name, step=step_name, instance_id=instance_id)
        conn.commit()
        return

      # Load instance data
      cur.execute("SELECT id, data FROM workflow_instances WHERE id = %s", (instance_id,))
      instance_row = cur.fetchone()
      if not instance_row:
        raise Reject(f"No instance found for id: {instance_id}", requeue=False)

      # Resolve connection credentials if connection_id is provided
      if connection_id:
        cur.execute("SELECT config FROM connections WHERE id = %s", (connection_id,))
        conn_row = cur.fetchone()
        if conn_row and conn_row["config"]:
          merged = dict(conn_row["config"])
          merged.update(config)
          config = merged
        else:
          log.warning("Connection not found, proceeding without it", connection_id=connection_id, action=action_name)

      # Find handler
      handler = self.registry.get_handler(action_name)
      if not handler:
        log.error("No handler found for action", action=action_name)
        raise Reject(f"No handler for action: {action_name}", requeue=False)

      # Execute handler — catch exceptions and convert to STEP_FAILED
      try:
        result: ActionResult = handler.execute(instance_id, instance_row["data"] or {}, config=config, task_context=task_context)
      except Exception as e:
        log.error("Action handler raised exception", action=action_name, error=str(e), exc_info=True)
        result = ActionResult(status=ActionStatus.FAILURE, error_message=str(e))

      # Send result back to orchestrator via outbox
      event_type = STEP_COMPLETE_EVENT if result.status == ActionStatus.SUCCESS else STEP_FAILED_EVENT
      payload = {"type": event_type, "instance_id": str(instance_id), "step_name": step_name}
      if result.updated_data:
        payload["data"] = result.updated_data

      cur.execute(
        "INSERT INTO outbox (destination, payload) VALUES (%s, %s)",
        (ORCHESTRATION_QUEUE, json.dumps(payload))
      )

      conn.commit()
      log.info("Action finished", action=action_name, step=step_name, status=result.status.value)
    except Exception:
      conn.rollback()
      raise
    finally:
      cur.close()
      return_connection(conn)