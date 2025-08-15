import structlog

from shared.loggin_config import setup_logging
from shared.celery_app import app
from shared.db import get_db_connection

from src.worker.application.worker_service import WorkerService
from src.worker.adapter.postgres_repository import PostgresWorkflowState
from src.worker.adapter.action_registry import DictActionRegistry
from src.worker.handlers.fetch_invoice_handler import FetchInvoiceHandler

setup_logging()
log = structlog.get_logger()

state_repo = PostgresWorkflowState(get_db_connection)
registry = DictActionRegistry({
  "fetch_invoice": FetchInvoiceHandler(),
})

service = WorkerService(state_repo, registry, log)

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
  service.execute_action(message.get("action"), message.get("instance_id"))
