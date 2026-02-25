import json
from typing import Optional

from src.shared.base_repository import BaseRepository


class PostgresAPIRepository(BaseRepository):

    def find_active_version_by_name(self, name: str) -> Optional[dict]:
        return self.fetch_one(
            "SELECT v.id, v.definition FROM workflow_versions v "
            "JOIN workflows w ON v.workflow_id = w.id "
            "WHERE w.name = %s AND v.is_active = true;",
            (name,)
        )

    def create_workflow(self, name: str) -> str:
        return self.execute_returning(
            "INSERT INTO workflows (name) VALUES (%s) RETURNING id;", (name,))

    def create_version(self, workflow_id: str, version: int, definition: dict, is_active: bool = True) -> str:
        return self.execute_returning(
            "INSERT INTO workflow_versions (workflow_id, version, definition, is_active) "
            "VALUES (%s, %s, %s, %s) RETURNING id;",
            (workflow_id, version, json.dumps(definition), is_active)
        )

    def list_workflows(self) -> list:
        return self.fetch_all("""
            SELECT w.id, w.name, w.created_at, w.updated_at,
                   v.id AS version_id, v.version, v.is_active
            FROM workflows w
            LEFT JOIN workflow_versions v ON v.workflow_id = w.id AND v.is_active = true
            ORDER BY w.created_at DESC;
        """)

    def get_workflow(self, workflow_id: str) -> Optional[dict]:
        return self.fetch_one("SELECT * FROM workflows WHERE id = %s;", (workflow_id,))

    def get_active_version(self, workflow_id: str) -> Optional[dict]:
        return self.fetch_one(
            "SELECT id, version, definition, is_active, created_at "
            "FROM workflow_versions WHERE workflow_id = %s AND is_active = true "
            "ORDER BY version DESC LIMIT 1;",
            (workflow_id,)
        )

    def get_max_version(self, workflow_id: str) -> int:
        return self.fetch_one(
            "SELECT COALESCE(MAX(version), 0) AS max_version "
            "FROM workflow_versions WHERE workflow_id = %s;",
            (workflow_id,)
        )["max_version"]

    def deactivate_versions(self, workflow_id: str) -> None:
        self.execute(
            "UPDATE workflow_versions SET is_active = false WHERE workflow_id = %s;",
            (workflow_id,)
        )

    def create_instance(self, version_id: str, status: str, data: dict, request_id: str = None) -> str:
        return self.execute_returning(
            "INSERT INTO workflow_instances (workflow_version_id, status, data, request_id) "
            "VALUES (%s, %s, %s, %s) RETURNING id;",
            (version_id, status, json.dumps(data), request_id)
        )

    def get_instance(self, instance_id: str) -> Optional[dict]:
        return self.fetch_one("SELECT * FROM workflow_instances WHERE id = %s;", (instance_id,))

    def get_instance_with_definition(self, instance_id: str) -> Optional[dict]:
        return self.fetch_one(
            "SELECT i.status, i.current_step, v.definition "
            "FROM workflow_instances i "
            "JOIN workflow_versions v ON i.workflow_version_id = v.id "
            "WHERE i.id = %s;",
            (instance_id,)
        )

    def update_instance_status(self, instance_id: str, status: str) -> None:
        self.execute(
            "UPDATE workflow_instances SET status = %s WHERE id = %s;",
            (status, instance_id)
        )

    def schedule_outbox_message(self, destination: str, payload: dict) -> None:
        self.execute(
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
        return self.fetch_all(query, tuple(params))

    def list_step_executions(self, instance_id: str) -> list:
        return self.fetch_all(
            "SELECT id, step_name, status, attempts, started_at, completed_at, "
            "input_data, output_data, error_details "
            "FROM workflow_step_executions "
            "WHERE instance_id = %s "
            "ORDER BY started_at ASC;",
            (instance_id,)
        )

    # --- Recovery ---

    def find_stuck_instances(self, stale_seconds: int = 60) -> list:
        return self.fetch_all(
            "SELECT i.id, i.status, i.current_step, i.data, "
            "v.definition, w.name AS workflow_name "
            "FROM workflow_instances i "
            "JOIN workflow_versions v ON i.workflow_version_id = v.id "
            "JOIN workflows w ON v.workflow_id = w.id "
            "WHERE i.status IN ('pending', 'running') "
            "AND i.updated_at < NOW() - INTERVAL '%s seconds' "
            "ORDER BY i.created_at ASC",
            (stale_seconds,)
        )

    def find_latest_step_execution(self, instance_id: str, step_name: str) -> dict:
        return self.fetch_one(
            "SELECT id, step_name, status, output_data "
            "FROM workflow_step_executions "
            "WHERE instance_id = %s AND step_name = %s "
            "ORDER BY started_at DESC LIMIT 1;",
            (instance_id, step_name)
        )

    # --- Connections ---

    def create_connection(self, connector_id: str, name: str, config: dict) -> str:
        return self.execute_returning(
            "INSERT INTO connections (connector_id, name, config) "
            "VALUES (%s, %s, %s) RETURNING id;",
            (connector_id, name, json.dumps(config))
        )

    def list_connections(self, connector_id: str = None) -> list:
        if connector_id:
            return self.fetch_all(
                "SELECT id, connector_id, name, created_at, updated_at "
                "FROM connections WHERE connector_id = %s ORDER BY name;",
                (connector_id,)
            )
        return self.fetch_all(
            "SELECT id, connector_id, name, created_at, updated_at "
            "FROM connections ORDER BY connector_id, name;"
        )

    def get_connection(self, connection_id: str) -> Optional[dict]:
        return self.fetch_one(
            "SELECT id, connector_id, name, config, created_at, updated_at "
            "FROM connections WHERE id = %s;",
            (connection_id,)
        )

    def update_connection(self, connection_id: str, name: str, config: dict) -> None:
        self.execute(
            "UPDATE connections SET name = %s, config = %s WHERE id = %s;",
            (name, json.dumps(config), connection_id)
        )

    def delete_connection(self, connection_id: str) -> None:
        self.execute("DELETE FROM connections WHERE id = %s;", (connection_id,))

    def find_active_versions_by_trigger(self, connector_id: str, trigger_id: str) -> list:
        return self.fetch_all(
            "SELECT v.id, w.name AS workflow_name, v.definition "
            "FROM workflow_versions v "
            "JOIN workflows w ON v.workflow_id = w.id "
            "WHERE v.is_active = true "
            "AND v.definition->'trigger'->>'connector_id' = %s "
            "AND v.definition->'trigger'->>'trigger_id' = %s;",
            (connector_id, trigger_id)
        )
