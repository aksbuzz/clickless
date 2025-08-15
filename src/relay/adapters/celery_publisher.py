from src.relay.domain.ports import TaskPublisherPort

class CeleryTaskPublisher(TaskPublisherPort):
  def __init__(self, celery_app):
    self.celery_app = celery_app

  def publish(self, task_name: str, queue: str, payload: str) -> None:
    self.celery_app.send_task(
      name=task_name,
      args=[payload],
      queue=queue
    )