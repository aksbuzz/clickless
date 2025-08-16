import json
import psycopg2
from typing import Optional, Tuple
from datetime import datetime
from psycopg2.extras import RealDictCursor

from src.shared.logging_config import log

from src.orchestration.domain.models import (
  WorkflowDefinition, WorkflowInstance, WorkflowStatus
)
from src.orchestration.domain.ports import WorkflowRepositoryPort, UnitOfWorkPort


class PostgresWorkflowRepository(WorkflowRepositoryPort):
  def __init__(self, cursor):
    self.cursor = cursor
  
  def get_instance_with_definition(self, instance_id: str) -> Optional[Tuple[WorkflowInstance, WorkflowDefinition]]:
    self.cursor.execute("""
      SELECT
        i.id,
        i.definition_id,
        i.status,
        i.current_step,
        i.current_step_attempts as attempts,
        i.data,
        i.history,
        i.created_at,
        i.updated_at,
        d.definition
      FROM workflow_instances i
      JOIN workflow_definitions d ON i.definition_id = d.id
      WHERE i.id = %s
    """, (instance_id,))

    row = self.cursor.fetchone()
    if not row:
      return None
        
    instance = WorkflowInstance(
      id=str(row['id']),
      definition_id=str(row['definition_id']),
      status=WorkflowStatus(row['status']),
      current_step=row['current_step'],
      attempts=row['attempts'] or 0,
      data=row['data'] or {},
      history=row['history'] or []
    )
        
    definition = WorkflowDefinition(
        id=str(row['definition_id']),
        definition=row['definition']
    )

    return instance, definition
      
  def update_instance_status(self, instance_id: str, status: WorkflowStatus) -> None:
    self.cursor.execute("""
      UPDATE workflow_instances
      SET status = %s, updated_at = NOW()
      WHERE id = %s
    """, (status.value, instance_id,))

    log.info("Instance status updated", status=status.value)

  def update_history_and_data(self, instance_id, history_entry_json, data_to_merge):
    if data_to_merge:
      self.cursor.execute(
        """
          UPDATE workflow_instances
          SET 
              history = history || %s::jsonb,
              data = data || %s::jsonb,
              updated_at = NOW()
          WHERE id = %s
        """, 
        (history_entry_json, json.dumps(data_to_merge), instance_id,)
      )
    else:
      self.cursor.execute("""
        UPDATE workflow_instances
        SET 
          history = history || %s::jsonb,
          updated_at = NOW()
        WHERE id = %s
        """, 
        (history_entry_json, instance_id,)
      )

    log.info("Step result recorded in instance")

  def schedule_step(self, instance_id: str, step_name: str, attempts: int = 1, publish_at: Optional[datetime] = None) -> None:
    if publish_at is None:
      publish_at = datetime.utcnow()

    self.cursor.execute("""
      UPDATE workflow_instances
      SET 
        status = %s, 
        current_step = %s,
        current_step_attempts = %s,
        updated_at = NOW()
      WHERE id = %s
    """, (WorkflowStatus.RUNNING.value, step_name, attempts, instance_id,))

    outbox_payload = json.dumps({"action": step_name, "instance_id": instance_id})

    self.cursor.execute("""
      INSERT INTO outbox (destination, payload, publish_at, created_at)
      VALUES (%s, %s, %s, NOW())
    """, ('actions_queue', outbox_payload, publish_at))

    log.info("Step scheduled", step=step_name, attempts=attempts)


  def schedule_orchestration_event(self, instance_id: str, step_name: str, publish_at: Optional[datetime]):
    if publish_at is None:
      publish_at = datetime.utcnow()
    
    history_entry = json.dumps({"step": step_name, "status": "succeeded","resumed_at": publish_at.isoformat()})

    # Update history
    self.cursor.execute(
      "UPDATE workflow_instances " \
      "SET history = history || %s::jsonb, updated_at = NOW(), current_step = %s " \
      "WHERE id = %s; ",
      (history_entry, step_name, instance_id,)
    )

    # mark task as Done
    outbox_payload = json.dumps({"step": step_name, "type": "STEP_COMPLETE", "instance_id": str(instance_id)})

    self.cursor.execute(
      "INSERT INTO outbox (destination, payload, publish_at) " \
      "VALUES (%s, %s, %s); ",
      ('orchestration_queue', outbox_payload, publish_at,)
    )

class PostgresUnitOfWork(UnitOfWorkPort):
  workflow: PostgresWorkflowRepository

  def __init__(self, conn_string: str):
    self.conn_string = conn_string

  def __enter__(self):
    self.conn = psycopg2.connect(self.conn_string, cursor_factory=RealDictCursor)
    self.cursor = self.conn.cursor()
    
    self.workflow = PostgresWorkflowRepository(self.cursor)
    return self
  
  def __exit__(self, exc_type, exc_val, exc_tb):
    if exc_type:
      self.rollback()
    else:
      self.commit()
    
    self.workflow = None
    self.cursor.close()
    self.conn.close()

  def commit(self):
    self.conn.commit()

  def rollback(self):
    self.conn.rollback()