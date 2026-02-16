from src.shared.celery_app import app
from src.shared.constants import ACTIONS_QUEUE

from src.worker.application.worker_service import WorkerService
from src.worker.adapters.action_registry import DictActionRegistry
from src.worker.action_handlers.action_handlers import (
  FetchInvoiceHandler, ValidateInvoiceHandler, GenerateReportHandler,
  ArchiveReportHandler, InitialStepHandler, FinalStepHandler,
  LogHandler, HttpRequestHandler, SendWebhookHandler, TransformDataHandler,
)
from src.worker.action_handlers.slack import SlackSendMessageHandler
from src.worker.action_handlers.trello import TrelloCreateCardHandler, TrelloAddCommentHandler
from src.worker.action_handlers.github import GitHubCreateIssueHandler, GitHubAddCommentHandler
from src.worker.action_handlers.postgresql import PostgresQueryHandler, PostgresExecuteHandler
from src.worker.action_handlers.python_executor import PythonExecuteHandler

registry = DictActionRegistry({
  # Internal / demo actions
  "fetch_invoice": FetchInvoiceHandler(),
  "validate_invoice": ValidateInvoiceHandler(),
  "generate_report": GenerateReportHandler(),
  "archive_report": ArchiveReportHandler(),
  "initial_step": InitialStepHandler(),
  "final_step": FinalStepHandler(),
  "log": LogHandler(),
  "transform_data": TransformDataHandler(),
  # HTTP connector actions
  "http_request": HttpRequestHandler(),
  # Webhook connector actions
  "send_webhook": SendWebhookHandler(),
  # Slack connector actions
  "slack_send_message": SlackSendMessageHandler(),
  # Trello connector actions
  "trello_create_card": TrelloCreateCardHandler(),
  "trello_add_comment": TrelloAddCommentHandler(),
  # GitHub connector actions
  "github_create_issue": GitHubCreateIssueHandler(),
  "github_add_comment": GitHubAddCommentHandler(),
  # PostgreSQL connector actions
  "postgresql_query": PostgresQueryHandler(),
  "postgresql_execute": PostgresExecuteHandler(),
  # Python connector actions
  "python_execute": PythonExecuteHandler(),
})


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
