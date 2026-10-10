"""The index that lets retention find finished runs without scanning every run (migration 003)."""
import pathlib

import pytest

from src.engine.retention import FINISHED, PURGE_SQL

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "infrastructure" / "postgres" / "migrations" / "003_retention_index.sql"
INDEX = "idx_instances_finished"


def definition(conn):
    cur = conn.cursor()
    cur.execute("SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' AND indexname = %s", (INDEX,))
    row = cur.fetchone()
    return row["indexdef"] if row else None


@pytest.fixture
def keep_index(conn):
    """The migration tests drop the index; put it back whatever happens."""
    original = definition(conn)
    yield original
    cur = conn.cursor()
    cur.execute(f"DROP INDEX IF EXISTS {INDEX}")
    if original:
        cur.execute(original)


def test_a_fresh_database_has_the_index(conn):
    assert definition(conn) is not None


def test_the_index_covers_only_finished_runs(conn):
    text = definition(conn)
    assert "updated_at" in text and "completed" in text and "failed" in text and "cancelled" in text
    assert "pending" not in text and "running" not in text


def test_the_migration_builds_the_same_index_as_init_sql(conn, keep_index):
    cur = conn.cursor()
    cur.execute(f"DROP INDEX {INDEX}")
    assert definition(conn) is None
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    assert definition(conn) == keep_index


def test_the_migration_can_be_applied_twice(conn, keep_index):
    cur = conn.cursor()
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    assert definition(conn) == keep_index


def test_the_delete_query_can_use_the_index(conn):
    cur = conn.cursor()
    cur.execute("SET enable_seqscan = off")        # otherwise an empty table is always scanned
    try:
        cur.execute("EXPLAIN " + PURGE_SQL, (list(FINISHED), 30, 500))
        plan = "\n".join(next(iter(row.values())) for row in cur.fetchall())
    finally:
        cur.execute("RESET enable_seqscan")
    assert INDEX in plan, plan
