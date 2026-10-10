import structlog

from src.shared.logging_config import log
from src.engine import runtime
from src.shared.connectors.registry import ConnectorRegistry
from src.shared.db import db_cursor
from src.shared.triggers.models import TriggerEvent
from src.shared.triggers.ports import TriggerHandlerPort

from src.api.repository import WorkflowRepository
from src.api.errors import (
    WorkflowNotFoundError, InstanceNotFoundError,
    InvalidStateError, DuplicateWorkflowError, ValidationError,
    ConnectionNotFoundError, DuplicateConnectionError,
)
from src.api.health import HealthChecker


class WorkflowManagementService:
    def __init__(self, connector_registry: ConnectorRegistry):
        self.connector_registry = connector_registry

    def health_check(self) -> dict:
        with db_cursor() as cur:
            return HealthChecker.comprehensive_check(cur)

    def list_connectors(self) -> list:
        from dataclasses import asdict
        return [asdict(c) for c in self.connector_registry.list_connectors()]

    # --- Workflow CRUD ---

    def create_workflow(self, name: str, definition: dict) -> dict:
        errors = self.connector_registry.validate_definition(definition)
        if errors:
            raise ValidationError(errors)

        with db_cursor() as cur:
            repo = WorkflowRepository(cur)
            try:
                workflow_id = repo.create_workflow(name)
                version_id = repo.create_version(workflow_id, version=1, definition=definition)
            except Exception as e:
                if "unique" in str(e).lower():
                    raise DuplicateWorkflowError(f"Workflow name '{name}' already exists")
                raise

        log.info("Workflow created", workflow_id=workflow_id)
        return {"workflow_id": workflow_id, "version_id": version_id, "version": 1}

    def list_workflows(self) -> list:
        with db_cursor() as cur:
            return WorkflowRepository(cur).list_workflows()

    def get_workflow(self, workflow_id: str) -> dict:
        with db_cursor() as cur:
            repo = WorkflowRepository(cur)
            workflow = repo.get_workflow(workflow_id)
            if not workflow:
                raise WorkflowNotFoundError("Workflow not found")
            active_version = repo.get_active_version(workflow_id)

        result = dict(workflow)
        result["active_version"] = active_version
        return result

    def create_version(self, workflow_id: str, definition: dict) -> dict:
        errors = self.connector_registry.validate_definition(definition)
        if errors:
            raise ValidationError(errors)

        with db_cursor() as cur:
            repo = WorkflowRepository(cur)
            workflow = repo.get_workflow(workflow_id)
            if not workflow:
                raise WorkflowNotFoundError("Workflow not found")

            next_version = repo.get_max_version(workflow_id) + 1
            repo.deactivate_versions(workflow_id)
            version_id = repo.create_version(workflow_id, next_version, definition)

        log.info("New version created", workflow_id=workflow_id, version=next_version)
        return {"version_id": version_id, "version": next_version}

    # --- Workflow Execution ---

    def start_workflow(self, definition_name: str, data: dict) -> dict:
        log.info("Starting workflow", definition=definition_name)
        request_id = structlog.contextvars.get_contextvars().get("request_id")

        with db_cursor() as cur:
            instance_id = runtime.start_instance(cur, definition_name, data, request_id)

        log.info("Workflow started", instance_id=instance_id, request_id=request_id)
        return {"message": "Workflow started", "instance_id": instance_id}

    def trigger_webhook(self, workflow_name: str, data: dict) -> dict:
        log.info("Webhook received", workflow=workflow_name)
        request_id = structlog.contextvars.get_contextvars().get("request_id")

        with db_cursor() as cur:
            row = WorkflowRepository(cur).find_active_version_by_name(workflow_name)
            if not row:
                raise WorkflowNotFoundError("Workflow not found")

            definition = row["definition"]
            trigger = definition.get("trigger", {})
            if trigger.get("trigger_id") not in ("webhook_received", "http_request_received"):
                raise InvalidStateError("Workflow does not accept webhook triggers")

            instance_id = runtime.start_instance_for_version(
                cur, str(row["id"]), definition.get("start_at"), data, request_id)

        log.info("Workflow triggered via webhook", instance_id=instance_id, request_id=request_id)
        return {"message": "Workflow triggered", "instance_id": instance_id}

    # --- Instance Operations ---

    def list_instances(self, status: str = None, workflow_id: str = None, limit: int = 50, offset: int = 0) -> list:
        with db_cursor() as cur:
            return WorkflowRepository(cur).list_instances(status, workflow_id, limit, offset)

    def get_instance(self, instance_id: str) -> dict:
        with db_cursor() as cur:
            instance = WorkflowRepository(cur).get_instance(instance_id)
        if not instance:
            raise InstanceNotFoundError("Instance not found")
        return instance

    def cancel_instance(self, instance_id: str) -> dict:
        with db_cursor() as cur:
            runtime.cancel_instance(cur, instance_id)

        log.info("Workflow cancelled", instance_id=instance_id)
        return {"message": "Workflow cancelled", "instance_id": instance_id}

    def send_event(self, instance_id: str, data: dict) -> dict:
        with db_cursor() as cur:
            step = runtime.send_event(cur, instance_id, data)

        log.info("Event sent to resume workflow", instance_id=instance_id, step=step)
        return {"message": "Event received, workflow resuming", "instance_id": instance_id, "step": step}

    def process_external_trigger(self, event: TriggerEvent, handler: TriggerHandlerPort) -> list:
        log.info("Processing external trigger", connector_id=event.connector_id, trigger_id=event.trigger_id)
        request_id = structlog.contextvars.get_contextvars().get("request_id")

        started = []
        with db_cursor() as cur:
            versions = WorkflowRepository(cur).find_active_versions_by_trigger(event.connector_id, event.trigger_id)

            if not versions:
                log.info("No workflows matched trigger", connector_id=event.connector_id, trigger_id=event.trigger_id)
                return started

            for version_row in versions:
                definition = version_row["definition"]
                trigger_config = definition.get("trigger", {}).get("config", {})

                if not handler.matches_workflow_config(event, trigger_config):
                    continue

                instance_id = runtime.start_instance_for_version(
                    cur, str(version_row["id"]), definition.get("start_at"), event.data, request_id)
                started.append({"workflow_name": version_row["workflow_name"], "instance_id": instance_id})
                log.info("Workflow triggered", workflow=version_row["workflow_name"], instance_id=instance_id)

        return started

    def get_instance_steps(self, instance_id: str) -> list:
        with db_cursor() as cur:
            repo = WorkflowRepository(cur)
            instance = repo.get_instance(instance_id)
            if not instance:
                raise InstanceNotFoundError("Instance not found")
            return repo.list_step_executions(instance_id)

    # --- Connections ---

    def create_connection(self, connector_id: str, name: str, config: dict) -> dict:
        connector = self.connector_registry.get_connector(connector_id)
        if not connector:
            raise ValidationError([f"Unknown connector '{connector_id}'"])
        if not connector.connection_schema:
            raise ValidationError([f"Connector '{connector_id}' does not support connections"])

        with db_cursor() as cur:
            try:
                connection_id = WorkflowRepository(cur).create_connection(connector_id, name, config)
            except Exception as e:
                if "unique" in str(e).lower():
                    raise DuplicateConnectionError(f"Connection name '{name}' already exists for connector '{connector_id}'")
                raise

        log.info("Connection created", connection_id=connection_id, connector=connector_id)
        return {"connection_id": connection_id}

    def list_connections(self, connector_id: str = None) -> list:
        with db_cursor() as cur:
            return WorkflowRepository(cur).list_connections(connector_id)

    def get_connection(self, connection_id: str) -> dict:
        with db_cursor() as cur:
            connection = WorkflowRepository(cur).get_connection(connection_id)
        if not connection:
            raise ConnectionNotFoundError("Connection not found")
        return connection

    def update_connection(self, connection_id: str, name: str, config: dict) -> dict:
        with db_cursor() as cur:
            repo = WorkflowRepository(cur)
            existing = repo.get_connection(connection_id)
            if not existing:
                raise ConnectionNotFoundError("Connection not found")
            try:
                repo.update_connection(connection_id, name, config)
            except Exception as e:
                if "unique" in str(e).lower():
                    raise DuplicateConnectionError(f"Connection name '{name}' already exists for this connector")
                raise

        log.info("Connection updated", connection_id=connection_id)
        return {"message": "Connection updated"}

    def delete_connection(self, connection_id: str) -> dict:
        with db_cursor() as cur:
            repo = WorkflowRepository(cur)
            existing = repo.get_connection(connection_id)
            if not existing:
                raise ConnectionNotFoundError("Connection not found")
            repo.delete_connection(connection_id)

        log.info("Connection deleted", connection_id=connection_id)
        return {"message": "Connection deleted"}
