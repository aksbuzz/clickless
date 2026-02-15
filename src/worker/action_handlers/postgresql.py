import psycopg2
import psycopg2.extras

from src.shared.connectors.template import resolve_config
from src.shared.logging_config import log
from src.worker.domain.models import ActionStatus
from src.worker.domain.ports import ActionHandlerPort, ActionResult


class PostgresQueryHandler(ActionHandlerPort):
    def execute(self, instance_id, data, config=None, **kwargs):
        config = resolve_config(config or {}, data)
        connection_string = config.get("connection_string", "")
        query = config.get("query", "")
        params = config.get("params", [])

        if not connection_string:
            return ActionResult(ActionStatus.FAILURE, data, error_message="Missing 'connection_string' in config")
        if not query:
            return ActionResult(ActionStatus.FAILURE, data, error_message="Missing 'query' in config")

        log.info("Executing PostgreSQL query", instance_id=instance_id)
        try:
            conn = psycopg2.connect(connection_string)
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(query, params or None)
                    rows = [dict(row) for row in cur.fetchall()]
                    data["query_result"] = {"rows": rows, "row_count": len(rows)}
            finally:
                conn.close()

            log.info("PostgreSQL query executed", instance_id=instance_id, row_count=len(rows))
            return ActionResult(ActionStatus.SUCCESS, data)
        except psycopg2.Error as e:
            return ActionResult(ActionStatus.FAILURE, data, error_message=f"PostgreSQL error: {e}")
        except Exception as e:
            return ActionResult(ActionStatus.FAILURE, data, error_message=f"Unexpected error: {e}")


class PostgresExecuteHandler(ActionHandlerPort):
    def execute(self, instance_id, data, config=None, **kwargs):
        config = resolve_config(config or {}, data)
        connection_string = config.get("connection_string", "")
        query = config.get("query", "")
        params = config.get("params", [])

        if not connection_string:
            return ActionResult(ActionStatus.FAILURE, data, error_message="Missing 'connection_string' in config")
        if not query:
            return ActionResult(ActionStatus.FAILURE, data, error_message="Missing 'query' in config")

        log.info("Executing PostgreSQL statement", instance_id=instance_id)
        try:
            conn = psycopg2.connect(connection_string)
            try:
                with conn.cursor() as cur:
                    cur.execute(query, params or None)
                    rows_affected = cur.rowcount
                conn.commit()
                data["execute_result"] = {"rows_affected": rows_affected}
            finally:
                conn.close()

            log.info("PostgreSQL statement executed", instance_id=instance_id, rows_affected=rows_affected)
            return ActionResult(ActionStatus.SUCCESS, data)
        except psycopg2.Error as e:
            return ActionResult(ActionStatus.FAILURE, data, error_message=f"PostgreSQL error: {e}")
        except Exception as e:
            return ActionResult(ActionStatus.FAILURE, data, error_message=f"Unexpected error: {e}")
