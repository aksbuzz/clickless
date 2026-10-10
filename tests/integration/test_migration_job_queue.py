"""Upgrading a database created before the job queue (migration 002) gives the same schema as a fresh one."""
import os
import pathlib
import uuid

import psycopg2
import psycopg2.extras
import pytest
from psycopg2 import sql
from psycopg2.extensions import make_dsn

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD_SCHEMA = HERE / "schema_before_job_queue.sql"
NEW_SCHEMA = ROOT / "infrastructure" / "postgres" / "init.sql"
MIGRATION = ROOT / "infrastructure" / "postgres" / "migrations" / "002_job_queue.sql"


@pytest.fixture
def databases():
    admin_url = os.environ.get("TEST_DATABASE_URL")
    if not admin_url:
        if os.environ.get("CI"):
            pytest.fail("TEST_DATABASE_URL is not set")
        pytest.skip("TEST_DATABASE_URL is not set")
    admin = psycopg2.connect(admin_url)
    admin.autocommit = True
    created = []

    def make(schema_file):
        name = f"clickless_mig_{uuid.uuid4().hex[:8]}"
        admin.cursor().execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        created.append(name)
        conn = psycopg2.connect(make_dsn(admin_url, dbname=name), cursor_factory=psycopg2.extras.RealDictCursor)
        conn.autocommit = True
        conn.cursor().execute(schema_file.read_text(encoding="utf-8"))
        return conn

    yield make
    for name in created:
        admin.cursor().execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
    admin.close()


def table_shapes(conn):
    cur = conn.cursor()
    cur.execute("SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' ORDER BY table_name, column_name")
    columns = [tuple(r.values()) for r in cur.fetchall()]
    cur.execute("SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'public' ORDER BY indexname")
    indexes = [tuple(r.values()) for r in cur.fetchall()]
    return columns, indexes


def test_the_old_schema_really_is_the_old_one(databases):
    old = databases(OLD_SCHEMA)
    cur = old.cursor()
    cur.execute("SELECT to_regclass('outbox') IS NOT NULL AS has_outbox, to_regclass('jobs') IS NULL AS no_jobs")
    assert cur.fetchone() == {"has_outbox": True, "no_jobs": True}


def test_migration_gives_the_same_schema_as_a_fresh_database(databases):
    old, fresh = databases(OLD_SCHEMA), databases(NEW_SCHEMA)
    old.cursor().execute(MIGRATION.read_text(encoding="utf-8"))
    assert table_shapes(old) == table_shapes(fresh)


def test_migration_turns_unfinished_instances_into_jobs_and_leaves_the_rest(databases):
    old = databases(OLD_SCHEMA)
    cur = old.cursor()
    cur.execute("SELECT id FROM workflow_versions LIMIT 1")
    version = cur.fetchone()["id"]

    def instance(status, current_step=None):
        cur.execute("INSERT INTO workflow_instances (workflow_version_id, status, current_step, data) "
                    "VALUES (%s, %s, %s, '{}') RETURNING id", (version, status, current_step))
        return cur.fetchone()["id"]

    pending, running = instance("pending"), instance("running", "set_expedited")
    done, failed, cancelled = instance("completed"), instance("failed"), instance("cancelled")
    cur.execute("INSERT INTO outbox (destination, payload) VALUES ('actions_queue', '{}')")

    cur.execute(MIGRATION.read_text(encoding="utf-8"))

    cur.execute("SELECT instance_id, step_name, kind, status FROM jobs ORDER BY step_name")
    jobs = {str(r["instance_id"]): (r["step_name"], r["kind"], r["status"]) for r in cur.fetchall()}
    assert jobs == {
        str(pending): ("check_quantity", "run_step", "queued"),        # a pending instance starts at the definition's start_at
        str(running): ("set_expedited", "run_step", "queued"),          # a running one resumes at its current step
    }
    assert str(done) not in jobs and str(failed) not in jobs and str(cancelled) not in jobs
    cur.execute("SELECT to_regclass('outbox') IS NULL AS gone")
    assert cur.fetchone()["gone"] is True


def test_migration_can_be_applied_twice(databases):
    old = databases(OLD_SCHEMA)
    old.cursor().execute(MIGRATION.read_text(encoding="utf-8"))
    old.cursor().execute(MIGRATION.read_text(encoding="utf-8"))


MIGRATION_001 = ROOT / "infrastructure" / "postgres" / "migrations" / "001_add_request_id_tracing.sql"


def test_migration_001_still_applies_to_a_current_database(databases):
    """001 predates the job queue and touches the outbox; it must not break a database that no longer has one."""
    fresh = databases(NEW_SCHEMA)
    fresh.cursor().execute(MIGRATION_001.read_text(encoding="utf-8"))


def test_the_migrations_apply_in_order_to_a_database_from_before_both(databases):
    cur = databases(OLD_SCHEMA).cursor()
    cur.execute(MIGRATION_001.read_text(encoding="utf-8"))
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
