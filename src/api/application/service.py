import json
import structlog

from src.shared.logging_config import log
from src.shared.constants import ORCHESTRATION_QUEUE, ACTIONS_QUEUE
from src.shared.event_types import EventType
from src.shared.connectors.registry import ConnectorRegistry

from src.api.adapters.postgres_unit_of_work import PostgresAPIUnitOfWork
from src.api.domain.exceptions import (
  WorkflowNotFoundError, InstanceNotFoundError,
  InvalidStateError, DuplicateWorkflowError, ValidationError,
  ConnectionNotFoundError, DuplicateConnectionError,
)
from src.api.domain.health import HealthChecker
from src.shared.triggers.models import TriggerEvent
from src.shared.triggers.ports import TriggerHandlerPort

TERMINAL_STATUSES = ("completed", "failed", "cancelled")


class WorkflowManagementService:
  def __init__(self, uow: PostgresAPIUnitOfWork, connector_registry: ConnectorRegistry):
    self.uow = uow
    self.connector_registry = connector_registry

  def health_check(self) -> dict:
    """Perform comprehensive health check of all dependencies."""
    with self.uow:
      return HealthChecker.comprehensive_check(self.uow.repo.cursor)

  def list_connectors(self) -> list:
    from dataclasses import asdict
    return [asdict(c) for c in self.connector_registry.list_connectors()]

  # --- Workflow CRUD ---

  def create_workflow(self, name: str, definition: dict) -> dict:
    errors = self.connector_registry.validate_definition(definition)
    if errors:
      raise ValidationError(errors)

    with self.uow:
      try:
        workflow_id = self.uow.repo.create_workflow(name)
        version_id = self.uow.repo.create_version(workflow_id, version=1, definition=definition)
      except Exception as e:
        if "unique" in str(e).lower():
          raise DuplicateWorkflowError(f"Workflow name '{name}' already exists")
        raise

    log.info("Workflow created", workflow_id=workflow_id)
    return {"workflow_id": workflow_id, "version_id": version_id, "version": 1}

  def list_workflows(self) -> list:
    with self.uow:
      return self.uow.repo.list_workflows()

  def get_workflow(self, workflow_id: str) -> dict:
    with self.uow:
      workflow = self.uow.repo.get_workflow(workflow_id)
      if not workflow:
        raise WorkflowNotFoundError("Workflow not found")

      active_version = self.uow.repo.get_active_version(workflow_id)

    result = dict(workflow)
    result["active_version"] = active_version
    return result

  def create_version(self, workflow_id: str, definition: dict) -> dict:
    errors = self.connector_registry.validate_definition(definition)
    if errors:
      raise ValidationError(errors)

    with self.uow:
      workflow = self.uow.repo.get_workflow(workflow_id)
      if not workflow:
        raise WorkflowNotFoundError("Workflow not found")

      next_version = self.uow.repo.get_max_version(workflow_id) + 1
      self.uow.repo.deactivate_versions(workflow_id)
      version_id = self.uow.repo.create_version(workflow_id, next_version, definition)

    log.info("New version created", workflow_id=workflow_id, version=next_version)
    return {"version_id": version_id, "version": next_version}

  # --- Workflow Execution ---

  def start_workflow(self, definition_name: str, data: dict) -> dict:
    log.info("Starting workflow", definition=definition_name)

    # Get request_id from contextvars for distributed tracing
    request_id = structlog.contextvars.get_contextvars().get("request_id")

    with self.uow:
      row = self.uow.repo.find_active_version_by_name(definition_name)
      if not row:
        raise WorkflowNotFoundError("Workflow definition not found")

      version_id = str(row["id"])
      instance_id = self.uow.repo.create_instance(version_id, "pending", data, request_id)

      self.uow.repo.schedule_outbox_message(
        ORCHESTRATION_QUEUE,
        {"type": EventType.START_WORKFLOW.value, "instance_id": instance_id, "request_id": request_id}
      )

    log.info("Workflow started", instance_id=instance_id, request_id=request_id)
    return {"message": "Workflow started", "instance_id": instance_id}

  def trigger_webhook(self, workflow_name: str, data: dict) -> dict:
    log.info("Webhook received", workflow=workflow_name)

    # Get request_id from contextvars for distributed tracing
    request_id = structlog.contextvars.get_contextvars().get("request_id")

    with self.uow:
      row = self.uow.repo.find_active_version_by_name(workflow_name)
      if not row:
        raise WorkflowNotFoundError("Workflow not found")

      definition = row["definition"]
      trigger = definition.get("trigger", {})
      if trigger.get("trigger_id") not in ("webhook_received", "http_request_received"):
        raise InvalidStateError("Workflow does not accept webhook triggers")

      version_id = str(row["id"])
      instance_id = self.uow.repo.create_instance(version_id, "pending", data, request_id)

      self.uow.repo.schedule_outbox_message(
        ORCHESTRATION_QUEUE,
        {"type": EventType.START_WORKFLOW.value, "instance_id": instance_id, "request_id": request_id}
      )

    log.info("Workflow triggered via webhook", instance_id=instance_id, request_id=request_id)
    return {"message": "Workflow triggered", "instance_id": instance_id}

  # --- Instance Operations ---

  def list_instances(self, status: str = None, workflow_id: str = None, limit: int = 50, offset: int = 0) -> list:
    with self.uow:
      return self.uow.repo.list_instances(status, workflow_id, limit, offset)

  def get_instance(self, instance_id: str) -> dict:
    with self.uow:
      instance = self.uow.repo.get_instance(instance_id)
    if not instance:
      raise InstanceNotFoundError("Instance not found")
    return instance

  def cancel_instance(self, instance_id: str) -> dict:
    with self.uow:
      instance = self.uow.repo.get_instance(instance_id)
      if not instance:
        raise InstanceNotFoundError("Instance not found")

      if instance["status"] in TERMINAL_STATUSES:
        raise InvalidStateError(f"Cannot cancel instance with status '{instance['status']}'")

      self.uow.repo.update_instance_status(instance_id, "cancelled")

    log.info("Workflow cancelled", instance_id=instance_id)
    return {"message": "Workflow cancelled", "instance_id": instance_id}

  def send_event(self, instance_id: str, data: dict) -> dict:
    with self.uow:
      row = self.uow.repo.get_instance_with_definition(instance_id)
      if not row:
        raise InstanceNotFoundError("Instance not found")

      if row["status"] != "running":
        raise InvalidStateError(f"Instance is not running (status: '{row['status']}')")

      current_step = row["current_step"]
      if not current_step:
        raise InvalidStateError("Instance has no active step")

      definition = row["definition"]
      step_def = definition.get("steps", {}).get(current_step, {})
      if step_def.get("type") != "wait_for_event":
        raise InvalidStateError(f"Current step '{current_step}' is not a wait_for_event step")

      self.uow.repo.schedule_outbox_message(
        ORCHESTRATION_QUEUE,
        {
          "type": EventType.STEP_COMPLETE.value,
          "instance_id": instance_id,
          "step_name": current_step,
          "data": data,
        }
      )

    log.info("Event sent to resume workflow", instance_id=instance_id, step=current_step)
    return {"message": "Event received, workflow resuming", "instance_id": instance_id, "step": current_step}

  def process_external_trigger(self, event: TriggerEvent, handler: TriggerHandlerPort) -> list:
    log.info("Processing external trigger", connector_id=event.connector_id, trigger_id=event.trigger_id)

    # Get request_id from contextvars (may be None for external triggers)
    request_id = structlog.contextvars.get_contextvars().get("request_id")

    started = []
    with self.uow:
      versions = self.uow.repo.find_active_versions_by_trigger(event.connector_id, event.trigger_id)

      if not versions:
        log.info("No workflows matched trigger", connector_id=event.connector_id, trigger_id=event.trigger_id)
        return started

      for version_row in versions:
        definition = version_row["definition"]
        trigger_config = definition.get("trigger", {}).get("config", {})

        if not handler.matches_workflow_config(event, trigger_config):
          continue

        version_id = str(version_row["id"])
        instance_id = self.uow.repo.create_instance(version_id, "pending", event.data, request_id)

        self.uow.repo.schedule_outbox_message(
          ORCHESTRATION_QUEUE,
          {"type": EventType.START_WORKFLOW.value, "instance_id": instance_id, "request_id": request_id}
        )

        started.append({"workflow_name": version_row["workflow_name"], "instance_id": instance_id})
        log.info("Workflow triggered", workflow=version_row["workflow_name"], instance_id=instance_id, request_id=request_id)

    return started

  def recover_stuck_instances(self, stale_seconds: int = 60) -> list:
    """Find and re-queue events for stuck workflow instances."""
    recovered = []

    with self.uow:
      stuck = self.uow.repo.find_stuck_instances(stale_seconds)

      for instance in stuck:
        instance_id = str(instance["id"])
        status = instance["status"]
        current_step = instance["current_step"]
        definition = instance["definition"]

        if status == "pending":
          # Re-queue START_WORKFLOW
          self.uow.repo.schedule_outbox_message(
            ORCHESTRATION_QUEUE,
            {"type": EventType.START_WORKFLOW.value, "instance_id": instance_id}
          )
          recovered.append({"instance_id": instance_id, "action": "re-queued START_WORKFLOW"})
          log.info("Recovery: re-queued START_WORKFLOW", instance_id=instance_id)

        elif status == "running" and current_step:
          step_exec = self.uow.repo.find_latest_step_execution(instance_id, current_step)

          if step_exec and step_exec["status"] == "completed":
            # Worker finished but engine failed on transition — re-queue STEP_COMPLETE
            self.uow.repo.schedule_outbox_message(
              ORCHESTRATION_QUEUE,
              {
                "type": EventType.STEP_COMPLETE.value,
                "instance_id": instance_id,
                "step_name": current_step,
                "data": step_exec.get("output_data") or instance.get("data") or {},
              }
            )
            recovered.append({"instance_id": instance_id, "action": f"re-queued STEP_COMPLETE for {current_step}"})
            log.info("Recovery: re-queued STEP_COMPLETE", instance_id=instance_id, step=current_step)

          else:
            # Step execution still pending — re-dispatch action to worker
            step_def = definition.get("steps", {}).get(current_step, {})
            action_id = step_def.get("action_id", current_step)
            config = step_def.get("config", {})
            payload = {
              "action": action_id,
              "step_name": current_step,
              "instance_id": instance_id,
              "config": config,
            }
            connection_id = step_def.get("connection_id")
            if connection_id:
              payload["connection_id"] = connection_id
            self.uow.repo.schedule_outbox_message(ACTIONS_QUEUE, payload)
            recovered.append({"instance_id": instance_id, "action": f"re-dispatched action for {current_step}"})
            log.info("Recovery: re-dispatched action", instance_id=instance_id, step=current_step)

    return recovered

  def get_instance_steps(self, instance_id: str) -> list:
    with self.uow:
      instance = self.uow.repo.get_instance(instance_id)
      if not instance:
        raise InstanceNotFoundError("Instance not found")
      return self.uow.repo.list_step_executions(instance_id)

  # --- Connections ---

  def create_connection(self, connector_id: str, name: str, config: dict) -> dict:
    connector = self.connector_registry.get_connector(connector_id)
    if not connector:
      raise ValidationError([f"Unknown connector '{connector_id}'"])
    if not connector.connection_schema:
      raise ValidationError([f"Connector '{connector_id}' does not support connections"])

    with self.uow:
      try:
        connection_id = self.uow.repo.create_connection(connector_id, name, config)
      except Exception as e:
        if "unique" in str(e).lower():
          raise DuplicateConnectionError(f"Connection name '{name}' already exists for connector '{connector_id}'")
        raise

    log.info("Connection created", connection_id=connection_id, connector=connector_id)
    return {"connection_id": connection_id}

  def list_connections(self, connector_id: str = None) -> list:
    with self.uow:
      return self.uow.repo.list_connections(connector_id)

  def get_connection(self, connection_id: str) -> dict:
    with self.uow:
      connection = self.uow.repo.get_connection(connection_id)
    if not connection:
      raise ConnectionNotFoundError("Connection not found")
    return connection

  def update_connection(self, connection_id: str, name: str, config: dict) -> dict:
    with self.uow:
      existing = self.uow.repo.get_connection(connection_id)
      if not existing:
        raise ConnectionNotFoundError("Connection not found")
      try:
        self.uow.repo.update_connection(connection_id, name, config)
      except Exception as e:
        if "unique" in str(e).lower():
          raise DuplicateConnectionError(f"Connection name '{name}' already exists for this connector")
        raise
    log.info("Connection updated", connection_id=connection_id)
    return {"message": "Connection updated"}

  def delete_connection(self, connection_id: str) -> dict:
    with self.uow:
      existing = self.uow.repo.get_connection(connection_id)
      if not existing:
        raise ConnectionNotFoundError("Connection not found")
      self.uow.repo.delete_connection(connection_id)
    log.info("Connection deleted", connection_id=connection_id)
    return {"message": "Connection deleted"}
