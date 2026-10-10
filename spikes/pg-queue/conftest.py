import os
import pathlib
import sys

import psycopg2
import psycopg2.extras
import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))   # repo root, so `src.*` imports work
sys.path.insert(0, str(HERE))

DSN = os.environ.get("SPIKE_DSN", "postgresql://postgres@127.0.0.1:55432/spike")


@pytest.fixture(scope="session")
def dsn():
    try:
        conn = psycopg2.connect(DSN, connect_timeout=3)
    except psycopg2.OperationalError as exc:
        pytest.skip(f"no Postgres reachable at {DSN} (see README.md): {exc}")
    conn.autocommit = True
    conn.cursor().execute((HERE / "schema.sql").read_text())
    conn.close()
    return DSN


@pytest.fixture
def db(dsn):
    """Autocommit connection; every test starts with empty instances, executions and jobs."""
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = True
    conn.cursor().execute("TRUNCATE jobs, workflow_step_executions, workflow_instances CASCADE")
    yield conn
    conn.close()
