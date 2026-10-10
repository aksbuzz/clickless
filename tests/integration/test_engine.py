"""The Postgres-backed engine: one job per step, leases, retries, delays, events and cancellation."""
import threading
import time
import uuid
from datetime import datetime, timezone

import pytest

from src.engine import runtime
from src.engine.worker import StepRunner
from src.shared.db import db_cursor
from src.shared.errors import InstanceNotFoundError, InvalidStateError, WorkflowNotFoundError
from src.worker.registry import get_registry
from tests.integration.helpers import (
    Record, action, executions, instance, jobs, make_workflow, running_worker, start, terminal, wait_until,
)


@pytest.fixture
def handlers():
    return get_registry()   # the real handlers: transform_data, log, http_request, ...


# ---------------------------------------------------------------- the seed workflow, end to end

@pytest.mark.parametrize("quantity,priority,expedited,days", [(150, "high", True, 1), (30, "normal", False, 5)])
def test_seed_workflow_runs_to_completion_with_real_handlers(conn, handlers, quantity, priority, expedited, days):
    iid = start("order_priority_workflow", {"order": {"quantity": quantity}})
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    row = instance(conn, iid)
    assert row["status"] == "completed"
    assert row["current_step"] is None
    assert row["data"]["priority"] == priority
    assert row["data"]["expedited"] is expedited
    assert row["data"]["shipping_days"] == days
    steps = [(e["step_name"], e["status"]) for e in executions(conn, iid)]
    assert steps == [("check_quantity", "completed"),
                     (("set_expedited" if expedited else "set_standard"), "completed"), ("log_result", "completed")]
    assert jobs(conn, iid) == []                      # finished jobs are deleted


def test_a_step_stores_only_the_data_it_changed(conn, handlers):
    iid = start("order_priority_workflow", {"order": {"quantity": 150}})
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    step = [e for e in executions(conn, iid) if e["step_name"] == "set_expedited"][0]
    assert step["output_data"] == {"priority": "high", "expedited": True, "shipping_days": 1}


def test_templates_are_resolved_once_for_every_handler(conn, handlers):
    rec = Record()
    handlers["record"] = rec
    name = make_workflow(conn, {"start_at": "a", "steps": {
        "a": action("record", config={"message": "Order {{order.id}} is {{state}}"})}})
    iid = start(name, {"order": {"id": 7}, "state": "ready"})
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    assert rec.configs[0]["message"] == "Order 7 is ready"


def test_keys_a_handler_declares_untemplated_are_passed_through_as_written(conn, handlers):
    class SqlLike(Record):
        untemplated_keys = ("query",)

    rec = SqlLike()
    handlers["sqllike"] = rec
    name = make_workflow(conn, {"start_at": "a", "steps": {
        "a": action("sqllike", config={"query": "SELECT '{{user}}'", "params": ["{{user}}"]})}})
    iid = start(name, {"user": "bob'; --"})
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    assert rec.configs[0] == {"query": "SELECT '{{user}}'", "params": ["bob'; --"]}


def test_keys_removed_by_a_step_are_removed_from_the_instance_data(conn, handlers):
    name = make_workflow(conn, {"start_at": "a", "steps": {
        "a": {"type": "action", "connector_id": "internal", "action_id": "transform_data",
              "config": {"remove": ["secret"], "set": {"kept": 1}}}}})
    iid = start(name, {"secret": "s3cr3t", "other": 2})
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    assert instance(conn, iid)["data"] == {"other": 2, "kept": 1}


def test_the_request_id_of_the_start_request_follows_the_instance(conn, handlers):
    handlers["record"] = Record()
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("record", nxt="b"), "b": action("record")}})
    iid = start(name, {}, request_id="req-123")
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    assert instance(conn, iid)["request_id"] == "req-123"
    assert {e["request_id"] for e in executions(conn, iid)} == {"req-123"}


# ---------------------------------------------------------------- failure paths: always a visible outcome

def test_a_failing_step_fails_the_instance_and_records_the_error_text(conn, handlers):
    handlers["flaky"] = Record(fail_times=99)
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("flaky")}})
    iid = start(name, {})
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    assert instance(conn, iid)["status"] == "failed"
    assert executions(conn, iid)[0]["error_details"] == "boom 1"


def test_a_handler_that_raises_fails_the_step_with_the_exception(conn, handlers):
    class Raises:
        def execute(self, *args, **kwargs):
            raise RuntimeError("kaput")

    handlers["raises"] = Raises()
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("raises")}})
    iid = start(name, {})
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    assert instance(conn, iid)["status"] == "failed"
    assert "RuntimeError: kaput" in executions(conn, iid)[0]["error_details"]


def test_unknown_action_fails_the_instance_instead_of_stranding_it(conn, handlers):
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("does_not_exist")}})
    iid = start(name, {})
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    assert instance(conn, iid)["status"] == "failed"
    assert "no handler registered" in executions(conn, iid)[0]["error_details"]


def test_dangling_next_fails_the_instance(conn, handlers):
    handlers["record"] = Record()
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("record", nxt="nowhere")}})
    iid = start(name, {})
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    assert instance(conn, iid)["status"] == "failed"
    assert any("not defined" in (e["error_details"] or "") for e in executions(conn, iid))


def test_branch_cycle_is_stopped_by_the_inline_step_limit(conn, handlers):
    cond = {"field": "x", "operator": "exists"}
    name = make_workflow(conn, {"start_at": "a", "steps": {
        "a": {"type": "branch", "condition": cond, "on_true": "b", "on_false": "end"},
        "b": {"type": "branch", "condition": cond, "on_true": "a", "on_false": "end"}}})
    iid = start(name, {"x": 1})
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    assert instance(conn, iid)["status"] == "failed"
    assert any("cycle" in (e["error_details"] or "") for e in executions(conn, iid))


def test_missing_connection_fails_the_step_with_a_clear_message(conn, handlers):
    handlers["record"] = Record()
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("record", connection_id=str(uuid.uuid4()))}})
    iid = start(name, {})
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    assert instance(conn, iid)["status"] == "failed"
    assert "connection" in executions(conn, iid)[0]["error_details"]
    assert handlers["record"].calls == 0


def test_a_stored_connection_is_merged_under_the_step_config(conn, handlers):
    cur = conn.cursor()
    cur.execute("INSERT INTO connections (connector_id, name, config) VALUES ('x', 'main', %s) RETURNING id",
                ('{"token": "from-connection", "keep": 1}',))
    connection_id = str(cur.fetchone()["id"])
    rec = Record()
    handlers["record"] = rec
    name = make_workflow(conn, {"start_at": "a", "steps": {
        "a": action("record", connection_id=connection_id, config={"token": "step-wins", "extra": 2})}})
    iid = start(name, {})
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    assert rec.configs[0] == {"token": "step-wins", "keep": 1, "extra": 2}


# ---------------------------------------------------------------- retries

def test_retry_policy_then_success(conn, handlers):
    rec = Record(fail_times=2)
    handlers["flaky"] = rec
    name = make_workflow(conn, {"start_at": "a", "steps": {
        "a": action("flaky", retry={"max_attempts": 3, "delay_seconds": 0})}})
    iid = start(name, {})
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    assert instance(conn, iid)["status"] == "completed"
    assert rec.calls == 3
    assert [e["status"] for e in executions(conn, iid)] == ["failed", "failed", "completed"]
    assert [e["attempts"] for e in executions(conn, iid)] == [1, 2, 3]


def test_retries_exhausted_fails_the_instance_with_the_last_error(conn, handlers):
    rec = Record(fail_times=99)
    handlers["flaky"] = rec
    name = make_workflow(conn, {"start_at": "a", "steps": {
        "a": action("flaky", retry={"max_attempts": 3, "delay_seconds": 0})}})
    iid = start(name, {})
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    assert instance(conn, iid)["status"] == "failed"
    assert rec.calls == 3
    assert executions(conn, iid)[-1]["error_details"] == "boom 3"
    assert jobs(conn, iid)[0]["status"] == "dead"


# ---------------------------------------------------------------- delay and wait_for_event

def test_delay_is_a_future_run_at_and_the_worker_wakes_when_it_is_due(conn, handlers):
    rec = Record()
    handlers["record"] = rec
    name = make_workflow(conn, {"start_at": "first", "steps": {
        "first": action("record", nxt="pause"),
        "pause": {"type": "delay", "duration_seconds": 1, "next": "second"},
        "second": action("record")}})
    iid = start(name, {})
    with running_worker(handlers, idle_poll=30.0):          # no polling fallback: the wake-up must be exact
        wait_until(terminal(conn, iid))
    gap = rec.times[1] - rec.times[0]
    assert 1.0 <= gap < 2.0, gap
    assert instance(conn, iid)["status"] == "completed"


def test_wait_for_event_resumes_when_the_event_arrives(conn, handlers):
    handlers["record"] = Record()
    name = make_workflow(conn, {"start_at": "w", "steps": {
        "w": {"type": "wait_for_event", "timeout_seconds": 60, "next": "after"},
        "after": action("record")}})
    iid = start(name, {})
    with running_worker(handlers):
        wait_until(lambda: [e for e in executions(conn, iid) if e["status"] == "running"])
        with db_cursor() as cur:
            runtime.send_event(cur, iid, {"approved": True})
        wait_until(terminal(conn, iid))
    row = instance(conn, iid)
    assert row["status"] == "completed" and row["data"]["approved"] is True
    assert jobs(conn, iid) == []                      # the pending timeout job was removed


def test_wait_for_event_times_out_and_fails(conn, handlers):
    name = make_workflow(conn, {"start_at": "w", "steps": {
        "w": {"type": "wait_for_event", "timeout_seconds": 1, "next": "end"}}})
    iid = start(name, {})
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    assert instance(conn, iid)["status"] == "failed"
    assert "timed out" in executions(conn, iid)[0]["error_details"]


def test_an_event_for_an_instance_that_is_not_waiting_is_rejected(conn):
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("record")}})
    iid = start(name, {})
    with pytest.raises(InvalidStateError):
        with db_cursor() as cur:
            runtime.send_event(cur, iid, {})


# ---------------------------------------------------------------- crash safety

def test_job_of_a_crashed_worker_is_reclaimed_after_the_lease_expires(conn, handlers):
    rec = Record()
    handlers["record"] = rec
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("record")}})
    iid = start(name, {})
    with db_cursor() as cur:
        assert runtime.claim_job(cur, "crashed", 0.3) is not None        # takes the job, then "dies"
    survivor = StepRunner(handlers, worker_id="survivor", lease_seconds=30)
    assert survivor.run_one() is False                                    # lease still valid: nothing to do
    time.sleep(0.5)
    assert survivor.run_one() is True                                     # lease expired: reclaimed and executed
    assert instance(conn, iid)["status"] == "completed"
    assert rec.calls == 1


def test_stale_worker_result_is_discarded_after_its_job_was_reclaimed(conn, handlers):
    """At-least-once: the handler runs twice, but state advances exactly once."""
    slow, after = Record(sleep=1.2, slow_first_call_only=True), Record()
    handlers["slow_once"], handlers["after"] = slow, after
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("slow_once", nxt="b"), "b": action("after")}})
    iid = start(name, {})
    a = StepRunner(handlers, worker_id="A", lease_seconds=0.4)
    b = StepRunner(handlers, worker_id="B", lease_seconds=30)
    t = threading.Thread(target=a.run_one)
    t.start()                                       # A claims, its handler sleeps past the lease
    time.sleep(0.7)
    while b.run_one():                              # B reclaims step a (fast this time) and carries on to step b
        pass
    t.join(timeout=10)                              # A finally returns: its result must be discarded
    assert instance(conn, iid)["status"] == "completed"
    assert slow.calls == 2 and after.calls == 1     # the side effect repeated once, the next step did not
    assert [e["step_name"] for e in executions(conn, iid) if e["status"] == "completed"] == ["a", "b"]
    assert [e["error_details"] for e in executions(conn, iid) if e["status"] == "failed"] == ["worker lost (lease expired)"]


def test_a_step_that_keeps_killing_its_worker_is_marked_dead(conn, handlers, monkeypatch):
    monkeypatch.setattr(runtime, "MAX_CLAIMS", 2)
    handlers["record"] = Record()
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("record")}})
    iid = start(name, {})
    for _ in range(2):                              # MAX_CLAIMS claims that never finish
        with db_cursor() as cur:
            assert runtime.claim_job(cur, "w", 0.05) is not None
        time.sleep(0.1)
    with db_cursor() as cur:
        assert runtime.claim_job(cur, "w", 0.05) == {"poison": True}   # the next claim exceeds the cap
    with db_cursor() as cur:
        assert runtime.claim_job(cur, "w", 0.05) is None
    assert instance(conn, iid)["status"] == "failed"
    assert jobs(conn, iid)[0]["status"] == "dead"


def test_an_engine_error_releases_the_job_for_a_later_retry(conn, handlers, monkeypatch):
    handlers["record"] = Record()
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("record")}})
    iid = start(name, {})

    def explode(cur, job):
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(runtime, "begin_step", explode)
    runner = StepRunner(handlers, worker_id="w", lease_seconds=30)
    assert runner.run_one() is True                 # handled: the error is logged, not raised
    job = jobs(conn, iid)[0]
    assert job["status"] == "queued" and job["locked_by"] is None
    assert job["run_at"] > datetime.now(timezone.utc)          # backed off, not retried immediately
    assert instance(conn, iid)["status"] != "failed"


# ---------------------------------------------------------------- cancel

def test_cancel_during_a_running_step_discards_the_result_and_stops_the_workflow(conn, handlers):
    slow, nxt = Record(sleep=0.8, set_data={"marker": "should-not-appear"}), Record()
    handlers["slow"], handlers["nxt"] = slow, nxt
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("slow", nxt="b"), "b": action("nxt")}})
    iid = start(name, {})
    runner = StepRunner(handlers, worker_id="w", lease_seconds=30)
    t = threading.Thread(target=runner.run_one)
    t.start()
    wait_until(lambda: slow.calls == 1)
    with db_cursor() as cur:
        runtime.cancel_instance(cur, iid)
    t.join(timeout=10)
    row = instance(conn, iid)
    assert row["status"] == "cancelled"
    assert "marker" not in row["data"]
    assert nxt.calls == 0
    assert jobs(conn, iid) == []


def test_cancelling_a_finished_or_unknown_instance_is_an_error(conn, handlers):
    handlers["record"] = Record()
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("record")}})
    iid = start(name, {})
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    with pytest.raises(InvalidStateError):
        with db_cursor() as cur:
            runtime.cancel_instance(cur, iid)
    with pytest.raises(InstanceNotFoundError):
        with db_cursor() as cur:
            runtime.cancel_instance(cur, str(uuid.uuid4()))


def test_starting_an_unknown_workflow_is_an_error(conn):
    with pytest.raises(WorkflowNotFoundError):
        start("no_such_workflow", {})


# ---------------------------------------------------------------- concurrency

def test_many_instances_across_threads_run_every_step_exactly_once(conn, handlers):
    name = make_workflow(conn, {"start_at": "a", "steps": {
        "a": {"type": "action", "connector_id": "internal", "action_id": "transform_data",
              "config": {"set": {"a": 1}}, "next": "b"},
        "b": {"type": "action", "connector_id": "internal", "action_id": "log",
              "config": {"message": "n={{a}}"}, "next": "c"},
        "c": {"type": "action", "connector_id": "internal", "action_id": "transform_data",
              "config": {"set": {"c": 3}}, "next": "end"}}})
    n = 80
    for _ in range(n):
        start(name, {})
    with running_worker(handlers, concurrency=4, idle_poll=0.5):
        cur = conn.cursor()
        wait_until(lambda: (cur.execute("SELECT count(*) AS c FROM workflow_instances WHERE status = 'completed'") or cur.fetchone()["c"]) == n,
                   timeout=60, interval=0.1)
    cur = conn.cursor()
    cur.execute("SELECT step_name, count(*) AS c FROM workflow_step_executions WHERE status = 'completed' GROUP BY step_name")
    assert {r["step_name"]: r["c"] for r in cur.fetchall()} == {"a": n, "b": n, "c": n}
    cur.execute("SELECT count(*) AS c FROM jobs")
    assert cur.fetchone()["c"] == 0


# ---------------------------------------------------------------- NOTIFY is expensive: use it only where someone must be woken

def listen(database_url):
    import psycopg2
    listener = psycopg2.connect(database_url)
    listener.autocommit = True
    listener.cursor().execute(f"LISTEN {runtime.NOTIFY_CHANNEL}")
    return listener


def notifications(listener) -> int:
    time.sleep(0.2)
    listener.poll()
    count = len(listener.notifies)
    del listener.notifies[:]
    return count


def test_starting_a_workflow_notifies_the_workers(conn, database_url):
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("record")}})
    listener = listen(database_url)
    start(name, {})
    assert notifications(listener) == 1
    listener.close()


def test_finishing_a_step_does_not_notify_for_the_next_one(conn, handlers, database_url):
    """The worker that finishes a step claims the next job itself. A NOTIFY per step would make every
    committing transaction queue on PostgreSQL's global notify lock and cap the whole system."""
    handlers["record"] = Record()
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("record", nxt="b"), "b": action("record", nxt="c"),
                                                            "c": action("record")}})
    iid = start(name, {})
    listener = listen(database_url)
    notifications(listener)                          # discard the one from the start
    runner = StepRunner(handlers, worker_id="w", lease_seconds=30)
    while runner.run_one():
        pass
    assert instance(conn, iid)["status"] == "completed"
    assert notifications(listener) == 0
    listener.close()


def test_jobs_due_in_the_future_still_notify_so_a_sleeping_dispatcher_hears_about_them(conn, handlers, database_url):
    handlers["record"] = Record()
    name = make_workflow(conn, {"start_at": "a", "steps": {
        "a": action("record", nxt="pause"), "pause": {"type": "delay", "duration_seconds": 30, "next": "b"},
        "b": action("record")}})
    start(name, {})
    listener = listen(database_url)
    notifications(listener)
    runner = StepRunner(handlers, worker_id="w", lease_seconds=30)
    assert runner.run_one() is True                  # step a: queues step b for 30 s from now
    assert notifications(listener) >= 1
    listener.close()


def test_resuming_with_an_event_notifies_the_workers(conn, handlers, database_url):
    handlers["record"] = Record()
    name = make_workflow(conn, {"start_at": "w", "steps": {"w": {"type": "wait_for_event", "next": "a"}, "a": action("record")}})
    iid = start(name, {})
    runner = StepRunner(handlers, worker_id="w", lease_seconds=30)
    assert runner.run_one() is True                  # arms the wait
    listener = listen(database_url)
    with db_cursor() as cur:
        runtime.send_event(cur, iid, {})
    assert notifications(listener) >= 1
    listener.close()
