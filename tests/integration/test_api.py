import os
import pytest
import psycopg2
from psycopg2.extras import RealDictCursor
from testcontainers.postgres import PostgresContainer
from urllib.parse import urlparse
from pathlib import Path
from fastapi.testclient import TestClient

from api.main import app


def make_psycopg2_params(url: str):
    url = url.replace("+psycopg2", "")
    parsed = urlparse(url)
    return {
        "dbname": parsed.path.lstrip("/"),
        "user": parsed.username,
        "password": parsed.password,
        "host": parsed.hostname,
        "port": parsed.port,
    }


@pytest.fixture(scope="module")
def postgres_container():
    container = PostgresContainer()
    with container as pg:
        db_url = pg.get_connection_url().replace("+psycopg2", "")
        os.environ["DATABASE_URL"] = db_url
        yield pg


@pytest.fixture(scope="function", autouse=True)
def setup_database_schema(postgres_container):
    conn_params = make_psycopg2_params(postgres_container.get_connection_url())

    init_sql_path = Path(__file__).parent.parent.parent / "init.sql"
    if not init_sql_path.exists():
        raise FileNotFoundError(f"init.sql not found at: {init_sql_path}")

    init_sql = init_sql_path.read_text(encoding="utf-8")

    with psycopg2.connect(**conn_params) as conn:
        with conn.cursor() as cur:
            cur.execute(init_sql)

            cur.execute(
                """
                TRUNCATE workflow_instances, outbox, workflow_definitions
                RESTART IDENTITY CASCADE;
                """)

            cur.execute(
                """
                INSERT INTO workflow_definitions (name, definition)
                VALUES ('test_flow', '{"start_at": "step1"}');
                """)
        conn.commit()

    yield


def test_run_workflow(postgres_container):
    payload = {"data": {"customer_id": "cust-tc-123"}}

    # Act
    with TestClient(app) as client:
        response = client.post("/workflows/test_flow/run", json=payload)

    # Assert API response
    assert response.status_code == 200
    instance_id = response.json()["instance_id"]

    # Assert DB contents
    conn_params = make_psycopg2_params(postgres_container.get_connection_url())
    with psycopg2.connect(**conn_params) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM workflow_instances WHERE id = %s", (instance_id,))
            instance = cur.fetchone()
            assert instance is not None
            assert instance["status"] == "PENDING"
            assert instance["data"]["customer_id"] == "cust-tc-123"

            cur.execute("SELECT * FROM outbox;")
            outbox_msg = cur.fetchone()
            assert outbox_msg is not None
            assert outbox_msg["destination"] == "orchestration_queue"
            assert outbox_msg["payload"]["instance_id"] == instance_id
