import structlog
from src.core.logging_config import setup_logging

setup_logging()
log = structlog.get_logger()

import os
import time
import pika
import psycopg2

from src.core.db import get_db_connection
from src.core.celery_app import app as celery_app


RABBITMQ_URL = os.getenv("RABBITMQ_URL")

TASK_ROUTING = {
  'orchestration_queue': 'engine.orchestrate',
  'actions_queue': 'worker.execute_action'
}

def main():
  log.info("Starting Relay services...")
  
  while True:
    try:
      with get_db_connection() as db_conn:
        with db_conn.cursor() as cur:
          cur.execute(
            "SELECT id, destination, payload " \
            "FROM outbox " \
            "WHERE processed_at IS NULL AND publish_at <= NOW() " \
            "ORDER BY publish_at " \
            "LIMIT 100; "
          )
          messages = cur.fetchall()
          
          if not messages:
            time.sleep(1)
            continue

          processed_ids = []
          for msg_id, destination, payload in messages:
            task_name = TASK_ROUTING.get(destination)
            if not task_name:
              log.error("No task mapping found for destination. Skipping message.", destination=destination, msg_id=msg_id)
              continue
            
            try:
              celery_app.send_task(
                name=task_name,
                args=[payload],
                queue=destination
              )
              processed_ids.append(str(msg_id))
            except Exception as send_err:
              log.error("Failed to send task via Celery. Will retry", msg_id=msg_id, send_err=send_err)
              break

          # Update processed messages in DB
          if processed_ids:
            cur.execute(
              "UPDATE outbox " \
              "SET processed_at = NOW() " \
              "WHERE id = ANY(%s::uuid[]); ",
              (processed_ids,)
            )
            db_conn.commit()
            log.info("Relayed messages successfully.", count=len(processed_ids))
    
    except (psycopg2.Error, pika.exceptions.AMQPConnectionError) as e:
        log.error("A recoverable error occurred. Retrying in 5 seconds.",  exc_info=True)
        time.sleep(5)
    except Exception as e:
        log.error("An unexpected error occurred in the relay loop. Retrying in 10 seconds.",  exc_info=True)
        time.sleep(10)

if __name__ == "__main__":
  main()