import psycopg2
import psycopg2.extensions
import psycopg2.extras

from src.shared.logging_config import log
from src.shared.net_guard import OutboundBlocked, check_host
from src.worker.models import ActionStatus, ActionResult
from src.worker.registry import action


def _guard_dsn(connection_string: str) -> None:
    """Refuse connection strings that point at internal hosts, or at no host (a local socket)."""
    try:
        params = psycopg2.extensions.parse_dsn(connection_string)
    except psycopg2.ProgrammingError as exc:
        raise OutboundBlocked("invalid connection string") from exc
    hosts = [h.strip() for key in ("host", "hostaddr") for h in params.get(key, "").split(",") if h.strip()]
    if not hosts:
        raise OutboundBlocked("the connection string must name a host (local socket connections are not allowed)")
    for host in hosts:
        check_host(host)


@action("postgresql_query")
class PostgresQueryHandler:
    # The engine resolves {{templates}} in a step's config, except for these keys. Values from triggers and
    # earlier steps must reach the database only as bound parameters, never as SQL text or as the connection.
    untemplated_keys = ("query", "connection_string")

    def execute(self, instance_id, data, config=None, **kwargs):
        config = config or {}   # {{params}} were already resolved by the engine
        connection_string = config.get("connection_string", "")
        query = config.get("query", "")
        params = config.get("params", [])

        if not connection_string:
            return ActionResult(ActionStatus.FAILURE, data, error_message="Missing 'connection_string' in config")
        if not query:
            return ActionResult(ActionStatus.FAILURE, data, error_message="Missing 'query' in config")

        try:
            _guard_dsn(connection_string)
        except OutboundBlocked as e:
            return ActionResult(ActionStatus.FAILURE, data, error_message=f"Blocked outbound connection: {e}")

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


@action("postgresql_execute")
class PostgresExecuteHandler:
    # The engine resolves {{templates}} in a step's config, except for these keys. Values from triggers and
    # earlier steps must reach the database only as bound parameters, never as SQL text or as the connection.
    untemplated_keys = ("query", "connection_string")

    def execute(self, instance_id, data, config=None, **kwargs):
        config = config or {}   # {{params}} were already resolved by the engine
        connection_string = config.get("connection_string", "")
        query = config.get("query", "")
        params = config.get("params", [])

        if not connection_string:
            return ActionResult(ActionStatus.FAILURE, data, error_message="Missing 'connection_string' in config")
        if not query:
            return ActionResult(ActionStatus.FAILURE, data, error_message="Missing 'query' in config")

        try:
            _guard_dsn(connection_string)
        except OutboundBlocked as e:
            return ActionResult(ActionStatus.FAILURE, data, error_message=f"Blocked outbound connection: {e}")

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
