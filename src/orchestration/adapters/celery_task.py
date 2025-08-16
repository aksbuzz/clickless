from celery.exceptions import Reject

from src.shared.celery_app import app
from src.shared.db import get_db_connection
from src.shared.redis_client import redis_client
from src.shared.logging_config import log

from src.orchestration.domain.events import WorkflowEvent
from src.orchestration.domain.models import EventType

from src.orchestration.adapters.postgres_unit_of_work import PostgresUnitOfWork
from src.orchestration.adapters.redis_lock import RedisLockService
from src.orchestration.application.orchestration_service import (
  OrchestrationService, RetryableError, NonRetryableError
)

unit_of_work = PostgresUnitOfWork(get_db_connection())
lock_service = RedisLockService(redis_client)
service = OrchestrationService(unit_of_work, lock_service)


@app.task(name="engine.orchestrate", queue="orchestration_queue", bind=True)
def orchestrate(self, message: dict):
  instance_id = message.get("instance_id")
  event_type = message.get("type")
  step_name = message.get("step")
  data = message.get("data")

  log.info("Processing orchestration event", event_type=event_type, step=step_name)

  try:
    event = WorkflowEvent(
      instance_id=instance_id,
      event_type=EventType(event_type),
      step_name=step_name,
      data=data
    )

    service.process_event(event)

    log.info("Orchestration event processed successfully", event_type=event_type)
  
  except RetryableError as e:
    log.warning("Retryable error occured", event_type=event_type, exc_info=True)
    raise self.retry(countdown=5, max_retries=12)
  
  except NonRetryableError as e:
    log.error("Non-Retryable error occured", event_type=event_type, exc_info=True)
    raise Reject(str(e), requeue=False)
  
  except Exception as e:
    log.error("Unexpected orchestration error", event_type=event_type, exc_info=True)
    raise self.retry(exc=e, countdown=10, max_retries=3)