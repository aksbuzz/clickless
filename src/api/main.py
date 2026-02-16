import os
import time

import structlog
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from uuid import UUID, uuid4
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from src.shared.logging_config import log
from src.shared.metrics import http_requests_total, http_request_duration_seconds
from src.shared.connectors.registry import registry as connector_registry
import src.shared.connectors.definitions  # noqa: F401 — registers connectors on import
from src.shared.triggers.registry import TriggerHandlerRegistry
from src.api.trigger_handlers.github import GitHubTriggerHandler
from src.api.trigger_handlers.slack import SlackTriggerHandler
from src.api.trigger_handlers.trello import TrelloTriggerHandler

from src.api.adapters.postgres_unit_of_work import PostgresAPIUnitOfWork
from src.api.application.service import WorkflowManagementService
from src.api.domain.exceptions import (
  WorkflowNotFoundError, InstanceNotFoundError,
  InvalidStateError, DuplicateWorkflowError, ValidationError,
  ConnectionNotFoundError, DuplicateConnectionError,
)

app = FastAPI()

app.add_middleware(
  CORSMiddleware,
  allow_origins=["http://localhost:5173"],
  allow_methods=["GET", "POST", "PUT", "DELETE"],
  allow_headers=["*"],
)

uow = PostgresAPIUnitOfWork()
service = WorkflowManagementService(uow, connector_registry)

trigger_registry = TriggerHandlerRegistry()
trigger_registry.register("github", GitHubTriggerHandler())
trigger_registry.register("slack", SlackTriggerHandler())
trigger_registry.register("trello", TrelloTriggerHandler())


@app.middleware("http")
async def logging_and_metrics_middleware(request: Request, call_next):
  # Set up logging context
  structlog.contextvars.clear_contextvars()
  request_id = str(uuid4())
  structlog.contextvars.bind_contextvars(request_id=request_id)

  # Track metrics
  start_time = time.time()
  response = await call_next(request)
  duration = time.time() - start_time

  # Record metrics (skip /metrics endpoint itself)
  if request.url.path != "/metrics":
    http_requests_total.labels(
      method=request.method,
      endpoint=request.url.path,
      status_code=response.status_code
    ).inc()

    http_request_duration_seconds.labels(
      method=request.method,
      endpoint=request.url.path
    ).observe(duration)

  structlog.contextvars.clear_contextvars()
  return response


# --- Request Models ---

class WorkflowPayload(BaseModel):
  data: dict

class CreateWorkflowPayload(BaseModel):
  name: str
  definition: dict

class CreateVersionPayload(BaseModel):
  definition: dict

class EventPayload(BaseModel):
  data: dict = {}

class CreateConnectionPayload(BaseModel):
  connector_id: str
  name: str
  config: dict

class UpdateConnectionPayload(BaseModel):
  name: str
  config: dict


# --- Health & Metrics ---

@app.get("/metrics")
def metrics():
  """Prometheus metrics endpoint."""
  return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
def health():
  """
  Comprehensive health check endpoint.

  Returns:
  - 200: All systems healthy
  - 503: One or more systems unhealthy (degraded)
  """
  try:
    result = service.health_check()
    # Return 503 if any component is unhealthy
    if result.get("status") != "healthy":
      raise HTTPException(status_code=503, detail=result)
    return result
  except HTTPException:
    raise
  except Exception as e:
    log.error("Health check failed", exc_info=True)
    raise HTTPException(status_code=503, detail={"status": "unhealthy", "error": str(e)})


@app.get("/ready")
def ready():
  """
  Lightweight readiness check (database only).
  Suitable for Kubernetes readiness probes.
  """
  try:
    with service.uow:
      service.uow.repo.cursor.execute("SELECT 1")
    return {"status": "ready"}
  except Exception:
    raise HTTPException(status_code=503, detail={"status": "not_ready"})


# --- Connector Discovery ---

@app.get("/connectors")
def list_connectors():
  return service.list_connectors()


# --- Connections ---

@app.post("/connections", status_code=201)
def create_connection(payload: CreateConnectionPayload):
  try:
    return service.create_connection(payload.connector_id, payload.name, payload.config)
  except ValidationError as e:
    raise HTTPException(status_code=400, detail={"validation_errors": e.errors})
  except DuplicateConnectionError as e:
    raise HTTPException(status_code=409, detail=str(e))


@app.get("/connections")
def list_connections(connector_id: str = None):
  return service.list_connections(connector_id)


@app.get("/connections/{connection_id}")
def get_connection(connection_id: UUID):
  try:
    return service.get_connection(str(connection_id))
  except ConnectionNotFoundError:
    raise HTTPException(status_code=404, detail="Connection not found")


@app.put("/connections/{connection_id}")
def update_connection(connection_id: UUID, payload: UpdateConnectionPayload):
  try:
    return service.update_connection(str(connection_id), payload.name, payload.config)
  except ConnectionNotFoundError:
    raise HTTPException(status_code=404, detail="Connection not found")
  except DuplicateConnectionError as e:
    raise HTTPException(status_code=409, detail=str(e))


@app.delete("/connections/{connection_id}")
def delete_connection(connection_id: UUID):
  try:
    return service.delete_connection(str(connection_id))
  except ConnectionNotFoundError:
    raise HTTPException(status_code=404, detail="Connection not found")


# --- Workflow CRUD ---

@app.post("/workflows", status_code=201)
def create_workflow(payload: CreateWorkflowPayload):
  try:
    return service.create_workflow(payload.name, payload.definition)
  except ValidationError as e:
    raise HTTPException(status_code=400, detail={"validation_errors": e.errors})
  except DuplicateWorkflowError as e:
    raise HTTPException(status_code=409, detail=str(e))


@app.get("/workflows")
def list_workflows():
  return service.list_workflows()


@app.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: UUID):
  try:
    return service.get_workflow(str(workflow_id))
  except WorkflowNotFoundError:
    raise HTTPException(status_code=404, detail="Workflow not found")


@app.post("/workflows/{workflow_id}/versions", status_code=201)
def create_version(workflow_id: UUID, payload: CreateVersionPayload):
  try:
    return service.create_version(str(workflow_id), payload.definition)
  except ValidationError as e:
    raise HTTPException(status_code=400, detail={"validation_errors": e.errors})
  except WorkflowNotFoundError:
    raise HTTPException(status_code=404, detail="Workflow not found")


# --- Workflow Execution ---

@app.post("/workflows/{definition_name}/run")
def run_workflow(definition_name: str, payload: WorkflowPayload):
  try:
    return service.start_workflow(definition_name, payload.data)
  except WorkflowNotFoundError:
    raise HTTPException(status_code=404, detail="Workflow definition not found")


@app.post("/webhooks/{workflow_name}")
def webhook_trigger(workflow_name: str, request: Request, payload: WorkflowPayload = None):
  """Trigger a workflow via webhook. Accepts any JSON body as workflow data."""
  try:
    data = payload.data if payload else {}
    return service.trigger_webhook(workflow_name, data)
  except WorkflowNotFoundError:
    raise HTTPException(status_code=404, detail="Workflow not found")
  except InvalidStateError as e:
    raise HTTPException(status_code=400, detail=str(e))


# --- Instance Operations ---

@app.get("/instances")
def list_instances(status: str = None, workflow_id: UUID = None, limit: int = 50, offset: int = 0):
  return service.list_instances(
    status=status,
    workflow_id=str(workflow_id) if workflow_id else None,
    limit=limit,
    offset=offset,
  )


@app.get("/instances/{instance_id}")
def get_instance_status(instance_id: UUID):
  try:
    return service.get_instance(str(instance_id))
  except InstanceNotFoundError:
    raise HTTPException(status_code=404, detail="Instance not found")


@app.get("/instances/{instance_id}/steps")
def get_instance_steps(instance_id: UUID):
  try:
    return service.get_instance_steps(str(instance_id))
  except InstanceNotFoundError:
    raise HTTPException(status_code=404, detail="Instance not found")


@app.post("/instances/{instance_id}/cancel")
def cancel_instance(instance_id: UUID):
  try:
    return service.cancel_instance(str(instance_id))
  except InstanceNotFoundError:
    raise HTTPException(status_code=404, detail="Instance not found")
  except InvalidStateError as e:
    raise HTTPException(status_code=409, detail=str(e))


@app.post("/instances/{instance_id}/events")
def send_event(instance_id: UUID, payload: EventPayload):
  """Resume a workflow that is waiting for an external event."""
  try:
    return service.send_event(str(instance_id), payload.data)
  except InstanceNotFoundError:
    raise HTTPException(status_code=404, detail="Instance not found")
  except InvalidStateError as e:
    raise HTTPException(status_code=409, detail=str(e))


# --- External Trigger Webhooks ---

def _get_connector_config(connector_id: str) -> dict:
  """Load system-level signing secrets from environment variables."""
  if connector_id == "github":
    return {"webhook_secret": os.getenv("GITHUB_WEBHOOK_SECRET", "")}
  elif connector_id == "slack":
    return {"signing_secret": os.getenv("SLACK_SIGNING_SECRET", "")}
  return {}


@app.head("/triggers/{connector_id}/webhook")
def trigger_webhook_head(connector_id: str):
  """HEAD endpoint for Trello webhook URL verification."""
  handler = trigger_registry.get_handler(connector_id)
  if not handler:
    raise HTTPException(status_code=404, detail=f"Unknown connector: {connector_id}")
  return Response(status_code=200)


@app.post("/triggers/{connector_id}/webhook")
async def trigger_webhook_external(connector_id: str, request: Request):
  """Receives webhooks from external services and starts matching workflows."""
  handler = trigger_registry.get_handler(connector_id)
  if not handler:
    raise HTTPException(status_code=404, detail=f"Unknown connector: {connector_id}")

  body = await request.body()
  headers = {k.lower(): v for k, v in request.headers.items()}
  connector_config = _get_connector_config(connector_id)

  validation = handler.validate_webhook(headers, body, connector_config)
  if not validation.is_valid:
    log.warning("Webhook validation failed", connector=connector_id, error=validation.error_message)
    raise HTTPException(status_code=401, detail=validation.error_message)

  if validation.challenge_response is not None:
    return {"challenge": validation.challenge_response}

  try:
    events = handler.parse_events(headers, body)
  except Exception as e:
    log.error("Failed to parse webhook payload", connector=connector_id, error=str(e))
    raise HTTPException(status_code=400, detail="Failed to parse webhook payload")

  if not events:
    return {"message": "Acknowledged, no matching trigger events"}

  all_started = []
  for event in events:
    started = service.process_external_trigger(event, handler)
    all_started.extend(started)

  return {
    "message": f"Processed {len(events)} event(s), started {len(all_started)} workflow(s)",
    "triggered": all_started,
  }
