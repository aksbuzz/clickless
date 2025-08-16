import os
from celery import Celery
from kombu import Queue


RABBITMQ_URL = os.getenv("RABBITMQ_URL")

app = Celery('workflows', 
  broker=RABBITMQ_URL, 
  backend='redis://redis:6379/1',
  include=['src.orchestration.adapters.celery_task', 'src.worker.adapters.celery_task']
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
  Queue('orchestration_dlq', routing_key='orchestration_dlq', durable=True),
  Queue('actions_dlq', routing_key='actions_dlq', durable=True),
  
  # Main Q
  Queue('orchestration_queue', routing_key='orchestration.#', durable=True,
        queue_arguments={
          'x-dead-letter-exchange': '',
          'x-dead-letter-routing-key': 'orchestration_dlq'
        }),

  Queue('actions_queue', routing_key='actions.#', durable=True,
        queue_arguments={
          'x-dead-letter-exchange': '',
          'x-dead-letter-routing-key': 'actions_dlq'
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