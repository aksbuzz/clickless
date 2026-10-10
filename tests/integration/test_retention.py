"""Finished runs are deleted after the retention period; nothing that is still going to run ever is."""
import threading
import time
import uuid

import psycopg2
import pytest

from src.engine import retention
from src.engine.retention import Housekeeper, purge_finished
from src.shared.db import db_cursor
from src.shared.metrics import retention_deleted_total
from tests.integration.helpers import action, make_workflow


@pytest.fixture
def version_id(conn):
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("noop")}})
    cur = conn.cursor()
    cur.execute("SELECT v.id FROM workflow_versions v JOIN workflows w ON w.id = v.workflow_id WHERE w.name = %s", (name,))
    return cur.fetchone()["id"]


def add_run(conn, version_id, status="completed", age_days=100, steps=2, dead_job=False, queued_job=False):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO workflow_instances (workflow_version_id, status, data, created_at, updated_at) "
        "VALUES (%s, %s, '{}', now() - make_interval(days => %s), now() - make_interval(days => %s)) RETURNING id",
        (version_id, status, age_days, age_days))
    iid = cur.fetchone()["id"]
    for n in range(steps):
        cur.execute("INSERT INTO workflow_step_executions (instance_id, step_name, status, started_at) VALUES (%s, %s, 'completed', now())",
                    (iid, f"s{n}"))
    if dead_job:
        cur.execute("INSERT INTO jobs (instance_id, step_name, status) VALUES (%s, 'a', 'dead')", (iid,))
    if queued_job:
        cur.execute("INSERT INTO jobs (instance_id, step_name, status) VALUES (%s, 'a', 'queued')", (iid,))
    return iid


def count(conn, table, where="true", args=()):
    cur = conn.cursor()
    cur.execute(f"SELECT count(*) AS n FROM {table} WHERE {where}", args)
    return cur.fetchone()["n"]


def purge(days=30, batch_size=500):
    with db_cursor() as cur:
        return purge_finished(cur, days, batch_size)


def test_old_finished_runs_are_deleted_with_their_steps_and_dead_jobs(conn, version_id):
    add_run(conn, version_id, "failed", age_days=45, steps=3, dead_job=True)
    assert purge(30) == 1
    assert count(conn, "workflow_instances") == 0
    assert count(conn, "workflow_step_executions") == 0
    assert count(conn, "jobs") == 0


def test_recent_finished_runs_are_kept(conn, version_id):
    keep = add_run(conn, version_id, "completed", age_days=5)
    assert purge(30) == 0
    assert count(conn, "workflow_instances", "id = %s", (keep,)) == 1
    assert count(conn, "workflow_step_executions") == 2


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
def test_every_finished_status_is_deleted(conn, version_id, status):
    add_run(conn, version_id, status, age_days=100)
    assert purge(30) == 1


@pytest.mark.parametrize("status", ["pending", "running"])
def test_runs_that_have_not_finished_are_never_deleted_however_old(conn, version_id, status):
    add_run(conn, version_id, status, age_days=1000, queued_job=True)
    assert purge(30) == 0
    assert count(conn, "workflow_instances") == 1
    assert count(conn, "jobs") == 1
    assert count(conn, "workflow_step_executions") == 2


def test_the_cut_off_is_the_number_of_days_given(conn, version_id):
    add_run(conn, version_id, age_days=10)
    assert purge(11) == 0
    assert purge(9) == 1


def test_a_batch_deletes_at_most_batch_size_oldest_first(conn, version_id):
    oldest = add_run(conn, version_id, age_days=300)
    add_run(conn, version_id, age_days=200)
    add_run(conn, version_id, age_days=100)
    assert purge(30, batch_size=2) == 2
    survivors = {r["id"] for r in _all(conn, "SELECT id FROM workflow_instances")}
    assert oldest not in survivors and len(survivors) == 1


def _all(conn, query):
    cur = conn.cursor()
    cur.execute(query)
    return cur.fetchall()


def test_a_run_that_is_locked_is_skipped_not_waited_for(conn, version_id, database_url):
    locked = add_run(conn, version_id, age_days=100)
    free = add_run(conn, version_id, age_days=100)
    other = psycopg2.connect(database_url)          # another worker (or a cancel) holds the row
    try:
        other.cursor().execute("SELECT 1 FROM workflow_instances WHERE id = %s FOR UPDATE", (locked,))
        started = time.monotonic()
        assert purge(30) == 1
        assert time.monotonic() - started < 2
        assert count(conn, "workflow_instances", "id = %s", (locked,)) == 1
        assert count(conn, "workflow_instances", "id = %s", (free,)) == 0
    finally:
        other.rollback()
        other.close()
    assert purge(30) == 1                           # once released it goes too


@pytest.mark.parametrize("days", [0, -1])
def test_a_zero_or_negative_period_is_refused_rather_than_deleting_everything(conn, version_id, days):
    add_run(conn, version_id, age_days=0)
    with pytest.raises(ValueError, match="days"):
        purge(days)
    assert count(conn, "workflow_instances") == 1


def test_the_housekeeper_drains_every_batch_in_one_pass(conn, version_id):
    for _ in range(5):
        add_run(conn, version_id, age_days=100)
    keeper = Housekeeper(30, batch_size=2, pause=0)
    assert keeper.run_once() == 5
    assert count(conn, "workflow_instances") == 0


def test_the_housekeeper_counts_what_it_deletes(conn, version_id):
    for _ in range(3):
        add_run(conn, version_id, age_days=100)
    before = retention_deleted_total._value.get()
    Housekeeper(30, pause=0).run_once()
    assert retention_deleted_total._value.get() - before == 3


def run_in_thread(keeper):
    stop = threading.Event()
    thread = threading.Thread(target=keeper.run, args=(stop,), daemon=True)
    thread.start()
    return stop, thread


def test_the_housekeeper_runs_a_pass_after_the_initial_delay_and_then_on_the_interval(conn, version_id):
    keeper = Housekeeper(30, interval=0.1, initial_delay=0.1, pause=0)
    passes = []
    keeper.run_once = lambda: passes.append(time.monotonic()) or 0
    stop, thread = run_in_thread(keeper)
    time.sleep(0.6)
    stop.set()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert len(passes) >= 3


def test_a_failing_pass_is_logged_and_the_next_one_still_runs(conn):
    keeper = Housekeeper(30, interval=0.05, initial_delay=0.0, pause=0)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("database went away")
        return 0

    keeper.run_once = flaky
    stop, thread = run_in_thread(keeper)
    time.sleep(0.5)
    stop.set()
    thread.join(timeout=2)
    assert len(calls) >= 2


def test_stopping_returns_promptly_even_in_the_middle_of_a_long_wait(conn):
    keeper = Housekeeper(30, interval=3600, initial_delay=3600)
    stop, thread = run_in_thread(keeper)
    time.sleep(0.1)
    started = time.monotonic()
    stop.set()
    thread.join(timeout=3)
    assert not thread.is_alive() and time.monotonic() - started < 2


def test_the_default_period_is_thirty_days():
    assert retention.DEFAULT_RETENTION_DAYS == 30
