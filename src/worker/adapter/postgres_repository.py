import json
from psycopg2.extras import RealDictCursor

from src.worker.domain.models import ActionResult
from src.worker.domain.ports import WorkflowStatePort

class PostgresWorkflowState(WorkflowStatePort):
  def __init__(self, conn_factory):
    self.conn_factory = conn_factory

  def load_state(self, instance_id: str):
    with self.conn_factory() as conn:
      with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
          SELECT d.definition, i.data, i.history
          FROM workflow_instances i
          JOIN workflow_definitions d ON i.definition_id = d.id
          WHERE i.id = %s
        """, (instance_id,))
        row = cur.fetchone()
        if not row:
          raise ValueError(f"Instance {instance_id} not found")

    return row["definition"], row["data"] or {}, row["history"] or []

  def save_result(self, instance_id: str, action: str, result: ActionResult):
    history_entry = json.dumps({"step": action, "status": result.status})
    with self.conn_factory() as conn:
      with conn.cursor() as cur:
        cur.execute("""
          UPDATE workflow_instances
          SET data = %s,
            history = history || %s::jsonb,
            updated_at = NOW()
          WHERE id = %s
        """, (json.dumps(result.updated_data), history_entry, instance_id))

      conn.commit()

  def send_event(self, event_type: str, instance_id: str, step: str):
    payload = json.dumps({
      "type": event_type,
      "instance_id": str(instance_id),
      "step": step
    })

    with self.conn_factory() as conn:
      with conn.cursor() as cur:
        cur.execute("""
          INSERT INTO outbox (destination, payload)
          VALUES (%s, %s)
        """, ("orchestration_queue", payload))

      conn.commit()