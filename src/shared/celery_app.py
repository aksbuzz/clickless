import os
from celery import Celery
from kombu import Queue

from src.shared.constants import ORCHESTRATION_QUEUE, ACTIONS_QUEUE, ORCHESTRATION_DLQ, ACTIONS_DLQ

RABBITMQ_URL = os.getenv("RABBITMQ_URL")

app = Celery('workflows', 
  broker=RABBITMQ_URL, 
  backend='redis://redis:6379/1',
  include=['src.orchestration.entrypoint.celery_task', 'src.worker.entrypoint.celery_task']
)

app.conf.update(
  task_ack_late=True,
  worker_prefetch_multiplier=1,
  task_default_delivery_mode='persistent',
  task_soft_time_limit=300, 
  task_time_limit=360
)

app.conf.task_queues = (
  # DLQ
  Queue(ORCHESTRATION_DLQ, routing_key=ORCHESTRATION_DLQ, durable=True),
  Queue(ACTIONS_DLQ, routing_key=ACTIONS_DLQ, durable=True),

  # Main Q
  Queue(ORCHESTRATION_QUEUE, routing_key='orchestration.#', durable=True,
        queue_arguments={
          'x-dead-letter-exchange': '',
          'x-dead-letter-routing-key': ORCHESTRATION_DLQ
        }),

  Queue(ACTIONS_QUEUE, routing_key='actions.#', durable=True,
        queue_arguments={
          'x-dead-letter-exchange': '',
          'x-dead-letter-routing-key': ACTIONS_DLQ
        }),
)

app.conf.task_reject_on_worker_lost = True

import structlog
from celery.signals import task_prerun, task_postrun

@task_prerun.connect
def setup_celery_logging(sender=None, task_id=None, task=None, args=None, kwargs=None, **other):
  structlog.contextvars.clear_contextvars()
  
  message = args[0] if args else {}
  instance_id = message.get("instance_id")
  
  structlog.contextvars.bind_contextvars(
    celery_task_id=task_id,
    celery_task_name=task.name,
    instance_id=instance_id
  )

@task_postrun.connect
def cleanup_celery_logging(sender=None, task_id=None, **kwargs):
  structlog.contextvars.clear_contextvars()