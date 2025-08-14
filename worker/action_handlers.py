import structlog
from shared.loggin_config import setup_logging

setup_logging()
log = structlog.get_logger()

import time
import json
from datetime import datetime, timedelta

from shared.db import get_db_connection


def _handle_fetch_invoice(instance_id, data):
  log.info(f"Fetching invoice...", instance_id=instance_id)
  
  time.sleep(2) # Simulate n/w call
  
  amount = data.get('invoice_details', {}).get('amount', 0)
  data['invoice_details'] = {'amount': amount or 1200, 'customer': 'Big Corp'}
  
  return "succeeded", data

def _handle_validate_invoice(instance_id, data):
  log.info(f"Validating invoice...", instance_id=instance_id)
  amount = data.get('invoice_details', {}).get('amount', 0)
  # Simulate business error
  if amount > 1000:
    data['is_valid'] = True
    return "succeeded", data
  else:
    data['is_valid'] = False
    data['error'] = "Invoice amount is too low for this test."
    return "failed", data
  
def _handle_generate_report(instance_id, data):
  log.info(f"Generating PDF report...", instance_id=instance_id)
  report_content = f"Invoice Report for {data['invoice_details']['customer']}\nAmount: ${data['invoice_details']['amount']}"
  
  data['report_content'] = report_content
  return "succeeded", data

def _handle_archive_report(instance_id, data, task_context):
  current_attempt = task_context.request.retries + 1

  # Simulate action failing due to transient errors
  if task_context.request.retries < 2:
    log.error("Simulating archive failure", attempt=current_attempt, instance_id=instance_id)
    raise ConnectionError("Archive S3 simulation failed")
  
  log.info("Archiving report to S3...",attempt=current_attempt, instance_id=instance_id)  
  object_name = f"{instance_id}/report.txt"

  time.sleep(2) # Simulate storing to S3
  data['report_archive_path'] = f"s3://bucket/{object_name}"
  
  if 'report_content' in data:
    del data['report_content']

  return "succeeded", data


def _handle_initial_step(instance_id, data):
  log.info(f"Executing the initial step.", instance_id=instance_id)
  data['initial_step_done'] = True
  return "succeeded", data

def _handle_final_step(instance_id, data):
  log.info(f"Executing the final step after the delay.", instance_id=instance_id)
  data['final_step_done'] = True
  return "succeeded", data



# SYSTEM ACTION

def _handle_delay_step(instance_id, step_name, step_definition):
  duration = step_definition.get("duration_seconds", 60)
  resume_at = datetime.utcnow() + timedelta(seconds=duration)

  log.info(f"Delay action initiated. Resuming after {resume_at.isoformat()}.", step_name=step_name, instance_id=instance_id)

  with get_db_connection() as conn:
    with conn.cursor() as cur:
      history_entry = json.dumps({
        "step": step_name,
        "status": "succeeded",
        "resumed_at": resume_at.isoformat()
      })

      # Set workflow status to paused
      cur.execute(
        "UPDATE workflow_instances " \
        "SET status = 'PAUSED', history = history || %s::jsonb, updated_at = NOW() " \
        "WHERE id = %s; ",
        (history_entry, instance_id, )
      )

      # In future, engine will complete the step
      outbox_payload = json.dumps({
        "type": "STEP_COMPLETE",
        "instance_id": str(instance_id)
      })

      cur.execute(
        "INSERT INTO outbox (destination, payload, publish_at) " \
        "VALUES (%s, %s, %s); ",
        ('orchestration_queue', outbox_payload, resume_at,)
      )
      conn.commit()


ACTION_HANDLERS = {
  "fetch_invoice": _handle_fetch_invoice,
  "validate_invoice": _handle_validate_invoice,
  "generate_report": _handle_generate_report,
  "archive_report": _handle_archive_report,
  "initial_step": _handle_initial_step,
  "final_step": _handle_final_step,

  # SYSTEM TASK
  "delay": _handle_delay_step,
}