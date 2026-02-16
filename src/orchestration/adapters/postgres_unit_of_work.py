import json
from typing import Optional, Tuple
from datetime import datetime, timezone

from src.shared.logging_config import log
from src.shared.base_unit_of_work import BasePostgresUnitOfWork

from src.orchestration.domain.models import (
  WorkflowVersion, WorkflowInstance, WorkflowStatus, WorkflowStepExecution
)
from src.orchestration.domain.ports import WorkflowRepositoryPort, UnitOfWorkPort


class PostgresWorkflowRepository(WorkflowRepositoryPort):
  def __init__(self, cursor):
    self.cursor = cursor

  def find_instance(self, instance_id: str) -> Optional[Tuple[WorkflowInstance, WorkflowVersion]]:
    self.cursor.execute("""
      SELECT
        i.id, i.workflow_version_id, i.status, i.current_step,
        i.current_step_attempts, i.data, i.created_at, i.updated_at,
        v.definition, w.name as workflow_name
      FROM workflow_instances i
      JOIN workflow_versions v ON i.workflow_version_id = v.id
      JOIN workflows w ON v.workflow_id = w.id
      WHERE i.id = %s
    """, (instance_id,))

    row = self.cursor.fetchone()
    if not row:
      return None

    instance = WorkflowInstance(
      id=str(row['id']),
      workflow_version_id=str(row['workflow_version_id']),
      status=WorkflowStatus(row['status']),
      current_step=row['current_step'],
      current_step_attempts=row['current_step_attempts'] or 0,
      data=row['data'] or {},
      created_at=row['created_at'],
      updated_at=row['updated_at']
    )

    version = WorkflowVersion(
      id=str(row['workflow_version_id']),
      definition=row['definition'],
      workflow_name=row['workflow_name']
    )

    return instance, version
  
  def find_current_step_execution(self, instance_id: str, step_name: str) -> Optional[WorkflowStepExecution]:
    self.cursor.execute("""
      SELECT 
        id, instance_id, step_name, status, attempts, started_at,
        completed_at, input_data, output_data, error_details
      FROM workflow_step_executions
      WHERE instance_id = %s AND step_name = %s
      ORDER BY started_at DESC
      LIMIT 1
    """, (instance_id, step_name,))
    row = self.cursor.fetchone()
    return WorkflowStepExecution(**row) if row else None
  
  def save_instance(self, instance: WorkflowInstance) -> None:
    self.cursor.execute("""
      UPDATE workflow_instances SET
        status = %s,
        current_step = %s,
        current_step_attempts = %s,
        data = %s,
        updated_at = NOW()
      WHERE id = %s
    """, (
      instance.status.value,
      instance.current_step,
      instance.current_step_attempts,
      json.dumps(instance.data),
      instance.id,
    ))
    log.info("Saved instance state", instance_id=instance.id, status=instance.status.value)

  def add_step_execution(self, step: WorkflowStepExecution) -> None:
    self.cursor.execute("""
      INSERT INTO workflow_step_executions (id, instance_id, step_name, status,
        attempts, started_at, input_data, request_id)
      VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        step.id, step.instance_id, step.step_name, step.status.value,
        step.attempts, step.started_at, json.dumps(step.input_data) if step.input_data else None,
        step.request_id
    ))
    log.info("Added new step execution", instance_id=step.instance_id, step=step.step_name, request_id=step.request_id)


  def save_step_execution(self, step: WorkflowStepExecution) -> None:
    self.cursor.execute("""
      UPDATE workflow_step_executions SET
        status = %s,
        completed_at = %s,
        output_data = %s,
        error_details = %s
      WHERE id = %s
    """, (
      step.status.value,
      step.completed_at,
      json.dumps(step.output_data) if step.output_data else None,
      step.error_details,
      step.id
    ))
    log.info("Saved step execution state", step_execution_id=step.id, status=step.status.value)

  def schedule_message(self, destination: str, payload: dict, publish_at: Optional[datetime] = None, request_id: str = None) -> None:
    if publish_at is None:
      publish_at = datetime.now(timezone.utc)

    self.cursor.execute("""
      INSERT INTO outbox (destination, payload, publish_at, request_id, created_at)
      VALUES (%s, %s, %s, %s, NOW())
    """, (destination, json.dumps(payload), publish_at, request_id))
    log.info("Scheduled message for outbox", destination=destination, request_id=request_id)


class PostgresUnitOfWork(BasePostgresUnitOfWork, UnitOfWorkPort):

  def _create_repositories(self, cursor):
    self._local.workflow = PostgresWorkflowRepository(cursor)

  @property
  def workflow(self):
    return self._local.workflow