import structlog
from shared.loggin_config import setup_logging

setup_logging()
log = structlog.get_logger()

import json
from datetime import datetime, timedelta
from celery.exceptions import Reject

from shared.celery_app import app
from shared.db import get_db_connection
from shared.redis_client import redis_client


LOCK_TIMEOUT = 30


@app.task(name="engine.orchestrate", queue="orchestration_queue", bind=True)
def orchestrate(self, message: dict):
  instance_id = message.get("instance_id")
  event_type = message.get("type")
  lock_key = f"lock:instance:{instance_id}"

  # Leader election: ensure only one engine instance processes this message
  lock = redis_client.lock(lock_key, timeout=LOCK_TIMEOUT)
  if not lock.acquire(blocking=False):
    log.warning(f"Could not acquire lock. Another engine is handling it.")
    # Requeue the task with a delay
    raise orchestrate.retry(countdown=5, max_retries=12)
  
  
  try:
    log.info(f"Acquired lock. Orchestrating event '{event_type}'.")
    
    with get_db_connection() as conn:
      with conn.cursor() as cur:
        # Get current instance state and definition
        cur.execute(
          "SELECT i.*, d.definition " \
          "FROM workflow_instances i " \
          "JOIN workflow_definitions d ON i.definition_id = d.id "
          "WHERE i.id = %s; ",
          (instance_id,)
        )

        row = cur.fetchone()
        if not row:
          log.error("Instance not found in database.")
          raise Reject("Instance not found.", requeue=False)
        
        (id, def_id, status, current_step, attempts, data, history, _, _, definition) = row

        # Business Retry 
        if event_type == "STEP_FAILED":
          step_def = definition["steps"].get(current_step, {})
          retry_policy = step_def.get("retry")

          if retry_policy and attempts < retry_policy["max_attempts"]:
            log.warning(
              f"Step '{current_step}' failed. Scheduling retry.",
              attempts=attempts,
              max_attempt=retry_policy["max_attempts"]
            )
            
            # Schedule SAME step again
            delay_seconds = retry_policy.get("delay_seconds", 5)
            publish_time = datetime.utcnow() + timedelta(seconds=delay_seconds)
            schedule_step(cur, instance_id, current_step, attempts+1, publish_time)
            conn.commit() 
            return 

          else:
            log.error(f"Step '{current_step}' failed permanently.", step=current_step)
            cur.execute(
              "UPDATE workflow_instances " \
              "SET status = 'FAILED' " \
              "WHERE id = %s; ",
              (instance_id,)
            )
            conn.commit()
            return

        next_step = None
        if event_type == "START_WORKFLOW":
          if status != 'PENDING':
            log.warning(f"Received START_WORKFLOW for already started instance. Ignoring.")
            return
          
          next_step = definition["start_at"]
        
        elif event_type == "STEP_COMPLETE":
          last_history_step = history[-1]['step'] if history else None
          step_def = definition["steps"].get(current_step, {})
          next_step = step_def.get("next") if step_def else "end"

          if last_history_step == next_step:
            log.warning(f"Received duplicate STEP_COMPLETE for {current_step}. Ignoring.")
            return

        # Workflow Completion or Next Step
        if not next_step or next_step == 'end':
          log.info("Workflow completed successfully.")
          cur.execute(
            "UPDATE workflow_instances " \
            "SET status = 'SUCCEEDED', updated_at = NOW() " \
            "WHERE id = %s; ",
            (instance_id,)
          )
        else:
          log.info(f"Scheduled step '{next_step}'")
          schedule_step(cur, instance_id, next_step)
        
        conn.commit()

  except Exception as e:
    log.error("Orchestration task failed unexpectedly.", exc_info=True)
    raise self.retry(exc=e, countdown=10, max_retries=3)
  
  finally:
    
    try:
      lock.release()
      log.info(f"Released lock")
    except Exception as e:
      log.warning("Could not release lock (it may have already expired).")


def schedule_step(cursor, instance_id, step_name, new_attempts=1, publish_at=None):
  """Helper function to update DB and create outbox message atomically."""
  if publish_at is None:
    publish_at = datetime.utcnow()
  
  cursor.execute(
    "UPDATE workflow_instances " \
    "SET status = 'RUNNING', current_step = %s, current_step_attempts = %s, updated_at = NOW() " \
    "WHERE id = %s; ",
    (step_name, new_attempts, instance_id,)
  )
  
  outbox_payload = json.dumps({
    "action": step_name,
    "instance_id": str(instance_id)
  })
  cursor.execute(
    "INSERT INTO outbox (destination, payload, publish_at) " \
    "VALUES (%s, %s, %s); ",
    ('actions_queue', outbox_payload, publish_at,)
  )