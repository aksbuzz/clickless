from src.shared.celery_app import app
from src.shared.constants import ACTIONS_QUEUE

from src.worker.application.worker_service import WorkerService
from src.worker.registry import get_registry

registry = get_registry()


@app.task(
    name="worker.execute_action",
    queue=ACTIONS_QUEUE,
    acks_late=True,
    bind=True,
)
def execute_action(self, message: dict):
    service = WorkerService(registry)
    service.execute_action(
        action_name=message.get("action"),
        instance_id=message.get("instance_id"),
        step_name=message.get("step_name"),
        config=message.get("config"),
        connection_id=message.get("connection_id"),
        task_context=self,
    )
