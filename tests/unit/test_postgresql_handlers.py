"""Values from triggers and earlier steps must reach SQL only as bound parameters.

Templating itself happens in the engine (see test_engine_steps.py and test_handlers_do_not_template.py); these
tests check that the handlers never rebuild the SQL or the connection string from the data."""
import pytest

from src.worker.handlers.postgresql import PostgresExecuteHandler, PostgresQueryHandler

HOSTILE = "x'; DROP TABLE orders; --"


class RecordingCursor:
    rowcount = 0

    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        self.log["executed"].append((query, params))

    def fetchall(self):
        return []


class RecordingConnection:
    def __init__(self, log):
        self.log = log

    def cursor(self, **kwargs):
        return RecordingCursor(self.log)

    def commit(self):
        pass

    def close(self):
        pass


@pytest.fixture
def db(monkeypatch):
    log = {"dsn": [], "executed": []}

    def connect(dsn, *args, **kwargs):
        log["dsn"].append(dsn)
        return RecordingConnection(log)

    monkeypatch.setattr("src.worker.handlers.postgresql.psycopg2.connect", connect)
    monkeypatch.setenv("OUTBOUND_ALLOW_PRIVATE", "true")   # these tests are about templating, not the network guard
    return log


HANDLERS = [PostgresQueryHandler, PostgresExecuteHandler]
DATA = {"user": HOSTILE, "db_host": "evil.internal", "order": {"id": 7}}


@pytest.mark.parametrize("handler", HANDLERS)
def test_query_text_is_used_exactly_as_written(db, handler):
    query = "SELECT * FROM orders WHERE owner = '{{user}}' AND id = {{order.id}}"
    result = handler().execute("i-1", dict(DATA), config={"connection_string": "postgresql://h/d", "query": query})
    assert result.status.value == "success"
    assert db["executed"][0][0] == query


@pytest.mark.parametrize("handler", HANDLERS)
def test_connection_string_is_never_templated(db, handler):
    handler().execute("i-1", dict(DATA), config={"connection_string": "postgresql://{{db_host}}/d", "query": "SELECT 1"})
    assert db["dsn"] == ["postgresql://{{db_host}}/d"]


def test_connector_form_text_describes_the_placeholder_style_psycopg2_uses():
    import src.shared.connectors.definitions  # noqa: F401 - registers the connectors
    from src.shared.connectors.registry import registry

    for action_id in ("postgresql_query", "postgresql_execute"):
        query_field = registry.get_action(action_id).config_schema["properties"]["query"]["description"]
        assert "%s" in query_field and "$1" not in query_field, f"{action_id}: {query_field}"
