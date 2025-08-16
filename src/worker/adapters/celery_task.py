from src.shared.celery_app import app
from src.shared.db import get_db_connection

from src.worker.application.worker_service import WorkerService
from src.worker.adapters.postgres_unit_of_work import PostgresUnitOfWork
from src.worker.adapters.action_registry import DictActionRegistry
from src.worker.action_handlers.action_handlers import (
  FetchInvoiceHandler, ValidateInvoiceHandler, GenerateReportHandler,
  ArchiveReportHandler, InitialStepHandler, FinalStepHandler
)

unit_of_work = PostgresUnitOfWork(get_db_connection())
registry = DictActionRegistry({
  "fetch_invoice": FetchInvoiceHandler(),
  "validate_invoice": ValidateInvoiceHandler(),
  "generate_report": GenerateReportHandler(),
  "archive_report": ArchiveReportHandler(),
  "initial_step": InitialStepHandler(),
  "final_step": FinalStepHandler(),
})

service = WorkerService(unit_of_work, registry)

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
  service.execute_action(message.get("action"), message.get("instance_id"), task_context=self)
