"""Integration tests run against a real PostgreSQL.

Set TEST_DATABASE_URL to a server where the user may create databases, for example
    docker run -d --name pg -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust postgres:17-alpine
    export TEST_DATABASE_URL=postgresql://postgres@localhost:5432/postgres
Each session creates a throwaway database from infrastructure/postgres/init.sql and drops it afterwards.
Without the variable the tests are skipped locally, and fail when CI is set so they cannot be skipped silently.
"""
import os
import pathlib
import uuid

import psycopg2
import psycopg2.extras
import pytest
from psycopg2 import sql
from psycopg2.extensions import make_dsn

from src.shared import db

INIT_SQL = pathlib.Path(__file__).resolve().parents[2] / "infrastructure" / "postgres" / "init.sql"


@pytest.fixture(scope="session")
def database_url():
    admin_url = os.environ.get("TEST_DATABASE_URL")
    if not admin_url:
        message = "TEST_DATABASE_URL is not set: integration tests need a PostgreSQL server (see tests/integration/conftest.py)"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)

    name = f"clickless_test_{uuid.uuid4().hex[:8]}"
    admin = psycopg2.connect(admin_url)
    admin.autocommit = True
    admin.cursor().execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = make_dsn(admin_url, dbname=name)

    conn = psycopg2.connect(url)
    conn.autocommit = True
    conn.cursor().execute(INIT_SQL.read_text(encoding="utf-8"))
    conn.close()

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    db.reset_pool()
    yield url
    db.reset_pool()
    if previous is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous
    admin.cursor().execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
    admin.close()


@pytest.fixture
def conn(database_url):
    """An autocommit connection for assertions. Every test starts with no instances, executions or jobs."""
    connection = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
    connection.autocommit = True
    connection.cursor().execute("TRUNCATE jobs, workflow_step_executions, workflow_instances CASCADE")
    yield connection
    connection.close()
