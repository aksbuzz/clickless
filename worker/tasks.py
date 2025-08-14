import structlog
from shared.loggin_config import setup_logging

setup_logging()
log = structlog.get_logger()

import json
import time

from celery.exceptions import Reject
from psycopg2.extras import RealDictCursor

from .action_handlers import ACTION_HANDLERS
from shared.celery_app import app
from shared.db import get_db_connection


@app.task(
  name="worker.execute_action", 
  queue="actions_queue", 
  acks_late=True, 
  bind=True, 
  autoretry_for=(Exception,), 
  max_retries=3,
  retry_backoff=True,
  retry_backoff_max=60
)
def execute_action(self, message: dict):
  action = message.get("action")
  instance_id = message.get("instance_id")
  
  with get_db_connection() as conn:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
      try:
        log.info("Starting action execution", action=action)
        
        # DELAY HANDLNG (System action)
        cur.execute(
          "SELECT d.definition, i.data, i.history " \
          "FROM workflow_instances i " \
          "JOIN workflow_definitions d ON i.definition_id = d.id " \
          "WHERE i.id = %s; ",
          (instance_id,)
        )
        row = cur.fetchone()
        if not row:
          raise Reject(f"Instance {instance_id} not found")

        definition = row['definition']
        current_data = row['data'] or {}
        history = row['history'] or []
        step_definition = definition.get('steps', {}).get(action, {})

        for entry in history:
          if entry.get("step") == action and entry.get('status') == 'succeeded':
            log.warning(f"Action '{action}' already completed. Ignoring")
            return # ACK and drop

        # Check if delay handler
        if 'duration_seconds' in step_definition:
          ACTION_HANDLERS.get('delay')(instance_id, action, step_definition)
          return

        # Normal Action
        handler = ACTION_HANDLERS.get(action)
        if not handler:
          raise ValueError(f"No handler for action: {action}")
        
        # Execute action
        # Simulate action failing first two times (Transient error)
        if action == 'archive_report':
          status, updated_data = handler(instance_id, current_data, self)
        else:
          status, updated_data = handler(instance_id, current_data)

        # Update instance with result and history
        history_entry = json.dumps({
          "step": action,
          "status": status,
          "timestamp": time.time()
        })
        cur.execute(
          "UPDATE workflow_instances " \
          "SET data = %s, history = history || %s::jsonb, updated_at = NOW() " \
          "WHERE id = %s; ",
          (json.dumps(updated_data), history_entry, instance_id,)
        )

        outbox_payload = json.dumps({
          "type": "STEP_COMPLETE" if status == "succeeded" else "STEP_FAILED",
          "instance_id": instance_id,
          "step": action
        })
        cur.execute(
          "INSERT INTO outbox (destination, payload) " \
          "VALUES (%s, %s); ",
          ('orchestration_queue', outbox_payload,)
        )
        conn.commit()
        log.info(f"Action completed", action=action, status=status)
      
      except Exception as e:
        conn.rollback()
        log.error("Action execution failed critically", action=action,  exc_info=True)
        raise e