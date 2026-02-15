import json
from typing import Optional


class PostgresAPIRepository:
  def __init__(self, cursor):
    self.cursor = cursor

  def find_active_version_by_name(self, name: str) -> Optional[dict]:
    self.cursor.execute(
      "SELECT v.id, v.definition FROM workflow_versions v "
      "JOIN workflows w ON v.workflow_id = w.id "
      "WHERE w.name = %s AND v.is_active = true;",
      (name,)
    )
    return self.cursor.fetchone()

  def create_workflow(self, name: str) -> str:
    self.cursor.execute(
      "INSERT INTO workflows (name) VALUES (%s) RETURNING id;",
      (name,)
    )
    return str(self.cursor.fetchone()["id"])

  def create_version(self, workflow_id: str, version: int, definition: dict, is_active: bool = True) -> str:
    self.cursor.execute(
      "INSERT INTO workflow_versions (workflow_id, version, definition, is_active) "
      "VALUES (%s, %s, %s, %s) RETURNING id;",
      (workflow_id, version, json.dumps(definition), is_active)
    )
    return str(self.cursor.fetchone()["id"])

  def list_workflows(self) -> list:
    self.cursor.execute("""
      SELECT w.id, w.name, w.created_at, w.updated_at,
             v.id AS version_id, v.version, v.is_active
      FROM workflows w
      LEFT JOIN workflow_versions v ON v.workflow_id = w.id AND v.is_active = true
      ORDER BY w.created_at DESC;
    """)
    return [dict(r) for r in self.cursor.fetchall()]

  def get_workflow(self, workflow_id: str) -> Optional[dict]:
    self.cursor.execute(
      "SELECT * FROM workflows WHERE id = %s;",
      (workflow_id,)
    )
    row = self.cursor.fetchone()
    return dict(row) if row else None

  def get_active_version(self, workflow_id: str) -> Optional[dict]:
    self.cursor.execute(
      "SELECT id, version, definition, is_active, created_at "
      "FROM workflow_versions WHERE workflow_id = %s AND is_active = true "
      "ORDER BY version DESC LIMIT 1;",
      (workflow_id,)
    )
    row = self.cursor.fetchone()
    return dict(row) if row else None

  def get_max_version(self, workflow_id: str) -> int:
    self.cursor.execute(
      "SELECT COALESCE(MAX(version), 0) AS max_version "
      "FROM workflow_versions WHERE workflow_id = %s;",
      (workflow_id,)
    )
    return self.cursor.fetchone()["max_version"]

  def deactivate_versions(self, workflow_id: str) -> None:
    self.cursor.execute(
      "UPDATE workflow_versions SET is_active = false WHERE workflow_id = %s;",
      (workflow_id,)
    )

  def create_instance(self, version_id: str, status: str, data: dict) -> str:
    self.cursor.execute(
      "INSERT INTO workflow_instances (workflow_version_id, status, data) "
      "VALUES (%s, %s, %s) RETURNING id;",
      (version_id, status, json.dumps(data))
    )
    return str(self.cursor.fetchone()["id"])

  def get_instance(self, instance_id: str) -> Optional[dict]:
    self.cursor.execute(
      "SELECT * FROM workflow_instances WHERE id = %s;",
      (instance_id,)
    )
    row = self.cursor.fetchone()
    return dict(row) if row else None

  def get_instance_with_definition(self, instance_id: str) -> Optional[dict]:
    self.cursor.execute(
      "SELECT i.status, i.current_step, v.definition "
      "FROM workflow_instances i "
      "JOIN workflow_versions v ON i.workflow_version_id = v.id "
      "WHERE i.id = %s;",
      (instance_id,)
    )
    row = self.cursor.fetchone()
    return dict(row) if row else None

  def update_instance_status(self, instance_id: str, status: str) -> None:
    self.cursor.execute(
      "UPDATE workflow_instances SET status = %s WHERE id = %s;",
      (status, instance_id)
    )

  def schedule_outbox_message(self, destination: str, payload: dict) -> None:
    self.cursor.execute(
      "INSERT INTO outbox (destination, payload) VALUES (%s, %s);",
      (destination, json.dumps(payload))
    )

  def list_instances(self, status: str = None, workflow_id: str = None, limit: int = 50, offset: int = 0) -> list:
    query = (
      "SELECT i.id, i.status, i.current_step, i.created_at, i.updated_at, "
      "w.name AS workflow_name, v.version "
      "FROM workflow_instances i "
      "JOIN workflow_versions v ON i.workflow_version_id = v.id "
      "JOIN workflows w ON v.workflow_id = w.id"
    )
    conditions = []
    params = []
    if status:
      conditions.append("i.status = %s")
      params.append(status)
    if workflow_id:
      conditions.append("w.id = %s")
      params.append(workflow_id)
    if conditions:
      query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY i.created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    self.cursor.execute(query, tuple(params))
    return [dict(r) for r in self.cursor.fetchall()]

  def list_step_executions(self, instance_id: str) -> list:
    self.cursor.execute(
      "SELECT id, step_name, status, attempts, started_at, completed_at, "
      "input_data, output_data, error_details "
      "FROM workflow_step_executions "
      "WHERE instance_id = %s "
      "ORDER BY started_at ASC;",
      (instance_id,)
    )
    return [dict(r) for r in self.cursor.fetchall()]

  def find_active_versions_by_trigger(self, connector_id: str, trigger_id: str) -> list:
    self.cursor.execute(
      "SELECT v.id, w.name AS workflow_name, v.definition "
      "FROM workflow_versions v "
      "JOIN workflows w ON v.workflow_id = w.id "
      "WHERE v.is_active = true "
      "AND v.definition->'trigger'->>'connector_id' = %s "
      "AND v.definition->'trigger'->>'trigger_id' = %s;",
      (connector_id, trigger_id)
    )
    return [dict(r) for r in self.cursor.fetchall()]
