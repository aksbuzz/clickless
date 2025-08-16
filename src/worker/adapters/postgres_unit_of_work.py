import json
import psycopg2
from psycopg2.extras import RealDictCursor

from src.worker.domain.models import ActionResult
from src.worker.domain.ports import WorkflowStatePort, UnitOfWorkPort

class PostgresWorkflowState(WorkflowStatePort):
  def __init__(self, cursor):
    self.cursor = cursor

  def load_state(self, instance_id: str):  
    self.cursor.execute("""
      SELECT d.definition, i.data, i.history
      FROM workflow_instances i
      JOIN workflow_definitions d ON i.definition_id = d.id
      WHERE i.id = %s
    """, (instance_id,))
    row = self.cursor.fetchone()
    if not row:
      raise ValueError(f"Instance {instance_id} not found")

    return row["definition"], row["data"] or {}, row["history"] or []

  # def save_result(self, instance_id: str, action: str, result: ActionResult):
  #   history_entry = json.dumps({"step": action, "status": result.status})
    
  #   self.cursor.execute("""
  #     UPDATE workflow_instances
  #     SET data = %s,
  #       history = history || %s::jsonb,
  #       updated_at = NOW()
  #     WHERE id = %s
  #   """, (json.dumps(result.updated_data), history_entry, instance_id))


  def send_event(self, event_type: str, instance_id: str, step: str, result_data: dict | None = None):
    payload = {
      "type": event_type,
      "instance_id": str(instance_id),
      "step": step
    }
    if result_data:
      payload["data"] = result_data

    self.cursor.execute("""
      INSERT INTO outbox (destination, payload)
      VALUES (%s, %s)
    """, ("orchestration_queue", json.dumps(payload)))


class PostgresUnitOfWork(UnitOfWorkPort):
  workflow: PostgresWorkflowState

  def __init__(self, conn_string: str):
    self.conn_string = conn_string

  def __enter__(self):
    self.conn = psycopg2.connect(self.conn_string, cursor_factory=RealDictCursor)
    self.cursor = self.conn.cursor()
    
    self.workflow = PostgresWorkflowState(self.cursor)
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