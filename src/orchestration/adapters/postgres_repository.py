import json
from typing import Optional, Tuple
from datetime import datetime
import structlog
from psycopg2.extras import RealDictCursor

from shared.loggin_config import setup_logging

from src.orchestration.domain.models import (
  WorkflowDefinition, WorkflowInstance, WorkflowStatus
)
from src.orchestration.domain.ports import WorkflowRepositoryPort

setup_logging()
log = structlog.get_logger()

class PostgresWorkflowRepository(WorkflowRepositoryPort):
  def __init__(self, conn_factory):
    self.conn_factory = conn_factory
  
  def get_instance_with_definition(self, instance_id: str) -> Optional[Tuple[WorkflowInstance, WorkflowDefinition]]:
    with self.conn_factory() as conn:
      with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
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

        row = cur.fetchone()
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
    with self.conn_factory() as conn:
      with conn.cursor() as cur:
        cur.execute("""
          UPDATE workflow_instances
          SET status = %s, updated_at = NOW()
          WHERE id = %s
        """, (status.value, instance_id,))
        
        conn.commit()
        log.info("Instance status updated", status=status.value)

  def schedule_step(self, instance_id: str, step_name: str, attempts: int = 1, publish_at: Optional[datetime] = None) -> None:
    if publish_at is None:
      publish_at = datetime.utcnow()

    with self.conn_factory() as conn:
      with conn.cursor() as cur:
        cur.execute("""
          UPDATE workflow_instances
          SET 
            status = %s, 
            current_step = %s,
            current_step_attempts = %s,
            updated_at = NOW()
          WHERE id = %s
        """, (WorkflowStatus.RUNNING.value, step_name, attempts, instance_id,))

        outbox_payload = json.dumps({"action": step_name, "instance_id": instance_id})

        cur.execute("""
          INSERT INTO outbox (destination, payload, publish_at, created_at)
          VALUES (%s, %s, %s, NOW())
        """, ('actions_queue', outbox_payload, publish_at))
        
        conn.commit()
        log.info("Step scheduled", step=step_name, attempts=attempts)