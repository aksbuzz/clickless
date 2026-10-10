"""Spike tests. They run the real connector handlers from src/worker against a real Postgres."""
import json
import os
import threading
import time
import uuid

import pytest

import pg_engine
from pg_engine import Engine
from src.worker.models import ActionResult, ActionStatus
from src.worker.registry import get_registry


# ---------------------------------------------------------------- helpers

class Record:
    """Handler that records every call, with a configurable behaviour."""
    def __init__(self, fail_times=0, sleep=0.0, slow_first_call_only=False, set_data=None):
        self.calls, self.configs, self.fail_times = 0, [], fail_times
        self.sleep, self.slow_first_only, self.set_data = sleep, slow_first_call_only, set_data or {}
        self.times = []

    def execute(self, instance_id, data, config=None, **kwargs):
        self.calls += 1
        call_no = self.calls
        self.configs.append(config)
        self.times.append(time.monotonic())
        if self.sleep and (call_no == 1 or not self.slow_first_only):
            time.sleep(self.sleep)
        if call_no <= self.fail_times:
            return ActionResult(ActionStatus.FAILURE, data, error_message=f"boom {call_no}")
        data.update(self.set_data)
        return ActionResult(ActionStatus.SUCCESS, data)


class Pool:
    def __init__(self, dsn, handlers, n=2, lease=30, max_sleep=5.0):
        self.dsn, self.stop, self.threads = dsn, threading.Event(), []
        for _ in range(n):
            t = threading.Thread(target=self._run, args=(handlers, lease, max_sleep), daemon=True)
            self.threads.append(t)

    def _run(self, handlers, lease, max_sleep):
        engine = Engine(self.dsn, handlers, lease_seconds=lease)
        try:
            engine.run_forever(self.stop, max_sleep=max_sleep)
        finally:
            engine.close()

    def __enter__(self):
        for t in self.threads:
            t.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        import psycopg2
        conn = psycopg2.connect(self.dsn)
        conn.autocommit = True
        conn.cursor().execute(f"NOTIFY {pg_engine.NOTIFY_CHANNEL}")   # wake sleepers so they see the stop flag
        conn.close()
        for t in self.threads:
            t.join(timeout=10)


@pytest.fixture
def handlers():
    registry = get_registry()   # the real handlers: python_execute, transform_data, log, http_request, ...
    return registry


@pytest.fixture
def engine(dsn, handlers):
    e = Engine(dsn, handlers, lease_seconds=30)
    yield e
    e.close()


def make_workflow(db, definition) -> str:
    name = f"spike_{uuid.uuid4().hex[:10]}"
    cur = db.cursor()
    cur.execute("INSERT INTO workflows (name) VALUES (%s) RETURNING id", (name,))
    wf = cur.fetchone()["id"]
    cur.execute("INSERT INTO workflow_versions (workflow_id, version, definition) VALUES (%s, 1, %s)",
                (wf, json.dumps(definition)))
    return name


def instance(db, iid):
    cur = db.cursor()
    cur.execute("SELECT * FROM workflow_instances WHERE id = %s", (iid,))
    return cur.fetchone()


def executions(db, iid):
    cur = db.cursor()
    cur.execute("SELECT * FROM workflow_step_executions WHERE instance_id = %s ORDER BY started_at, id", (iid,))
    return cur.fetchall()


def jobs(db, iid):
    cur = db.cursor()
    cur.execute("SELECT * FROM jobs WHERE instance_id = %s ORDER BY id", (iid,))
    return cur.fetchall()


def wait_until(predicate, timeout=15.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError("condition not met in time")


def terminal(db, iid):
    return lambda: instance(db, iid)["status"] in pg_engine.TERMINAL


def action(name, nxt="end", **extra):
    return {"type": "action", "connector_id": "x", "action_id": name, "next": nxt, **extra}


# ---------------------------------------------------------------- the seed workflow, end to end

@pytest.mark.parametrize("quantity,priority,expedited,days", [(150, "high", True, 1), (30, "normal", False, 5)])
def test_seed_workflow_runs_to_completion_with_real_handlers(db, dsn, handlers, engine, quantity, priority, expedited, days):
    iid = engine.start_workflow("order_priority_workflow", {"order": {"quantity": quantity}})
    with Pool(dsn, handlers):
        wait_until(terminal(db, iid))
    row = instance(db, iid)
    assert row["status"] == "completed"
    assert row["current_step"] is None
    assert row["data"]["priority"] == priority
    assert row["data"]["expedited"] is expedited
    assert row["data"]["shipping_days"] == days
    steps = [(e["step_name"], e["status"]) for e in executions(db, iid)]
    assert steps == [("compute_priority", "completed"), ("check_priority", "completed"),
                     (("set_expedited" if expedited else "set_standard"), "completed"), ("log_result", "completed")]
    assert all(j["status"] == "done" for j in jobs(db, iid))


def test_step_execution_stores_only_the_delta_not_the_whole_instance_data(db, dsn, handlers, engine):
    iid = engine.start_workflow("order_priority_workflow", {"order": {"quantity": 150}})
    with Pool(dsn, handlers):
        wait_until(terminal(db, iid))
    first = executions(db, iid)[0]
    assert first["output_data"] == {"priority": "high"}   # not {"order": ..., "priority": ...}
    assert first["input_data"] is None


def test_keys_removed_by_a_step_are_removed_from_the_instance_data(db, dsn, handlers, engine):
    name = make_workflow(db, {"start_at": "a", "steps": {
        "a": {"type": "action", "connector_id": "internal", "action_id": "transform_data",
              "config": {"remove": ["secret"], "set": {"kept": 1}}}}})
    iid = engine.start_workflow(name, {"secret": "s3cr3t", "other": 2})
    with Pool(dsn, handlers):
        wait_until(terminal(db, iid))
    assert instance(db, iid)["data"] == {"other": 2, "kept": 1}


def test_missing_connection_fails_the_step_with_a_clear_message(db, dsn, handlers, engine):
    handlers["record"] = Record()
    name = make_workflow(db, {"start_at": "a", "steps": {
        "a": action("record", connection_id=str(uuid.uuid4()))}})
    iid = engine.start_workflow(name, {})
    with Pool(dsn, handlers):
        wait_until(terminal(db, iid))
    assert instance(db, iid)["status"] == "failed"
    assert "connection" in executions(db, iid)[0]["error_details"]
    assert handlers["record"].calls == 0


def test_templates_are_resolved_centrally_for_every_handler(db, dsn, handlers, engine):
    rec = Record()
    handlers["record"] = rec
    name = make_workflow(db, {"start_at": "a", "steps": {
        "a": action("record", config={"message": "Order {{order.id}} is {{state}}"})}})
    iid = engine.start_workflow(name, {"order": {"id": 7}, "state": "ready"})
    with Pool(dsn, handlers):
        wait_until(terminal(db, iid))
    assert rec.configs[0]["message"] == "Order 7 is ready"


# ---------------------------------------------------------------- failure paths that strand instances today (F-08)

def test_unknown_action_fails_the_instance_instead_of_stranding_it(db, dsn, handlers, engine):
    name = make_workflow(db, {"start_at": "a", "steps": {"a": action("does_not_exist")}})
    iid = engine.start_workflow(name, {})
    with Pool(dsn, handlers):
        wait_until(terminal(db, iid))
    assert instance(db, iid)["status"] == "failed"
    assert "no handler registered" in executions(db, iid)[0]["error_details"]


def test_dangling_next_fails_the_instance(db, dsn, handlers, engine):
    handlers["record"] = Record()
    name = make_workflow(db, {"start_at": "a", "steps": {"a": action("record", nxt="nowhere")}})
    iid = engine.start_workflow(name, {})
    with Pool(dsn, handlers):
        wait_until(terminal(db, iid))
    assert instance(db, iid)["status"] == "failed"
    assert any("not defined" in (e["error_details"] or "") for e in executions(db, iid))


def test_branch_cycle_is_stopped_by_the_inline_step_limit(db, dsn, handlers, engine):
    cond = {"field": "x", "operator": "exists"}
    name = make_workflow(db, {"start_at": "a", "steps": {
        "a": {"type": "branch", "condition": cond, "on_true": "b", "on_false": "end"},
        "b": {"type": "branch", "condition": cond, "on_true": "a", "on_false": "end"}}})
    iid = engine.start_workflow(name, {"x": 1})
    with Pool(dsn, handlers):
        wait_until(terminal(db, iid))
    assert instance(db, iid)["status"] == "failed"
    assert any("cycle" in (e["error_details"] or "") for e in executions(db, iid))


# ---------------------------------------------------------------- retries

def test_retry_policy_then_success(db, dsn, handlers, engine):
    rec = Record(fail_times=2)
    handlers["flaky"] = rec
    name = make_workflow(db, {"start_at": "a", "steps": {
        "a": action("flaky", retry={"max_attempts": 3, "delay_seconds": 0})}})
    iid = engine.start_workflow(name, {})
    with Pool(dsn, handlers):
        wait_until(terminal(db, iid))
    assert instance(db, iid)["status"] == "completed"
    assert rec.calls == 3
    assert [e["status"] for e in executions(db, iid)] == ["failed", "failed", "completed"]


def test_retries_exhausted_fails_the_instance_with_the_last_error(db, dsn, handlers, engine):
    rec = Record(fail_times=99)
    handlers["flaky"] = rec
    name = make_workflow(db, {"start_at": "a", "steps": {
        "a": action("flaky", retry={"max_attempts": 3, "delay_seconds": 0})}})
    iid = engine.start_workflow(name, {})
    with Pool(dsn, handlers):
        wait_until(terminal(db, iid))
    assert instance(db, iid)["status"] == "failed"
    assert rec.calls == 3
    assert executions(db, iid)[-1]["error_details"] == "boom 3"
    assert jobs(db, iid)[0]["status"] == "dead"


# ---------------------------------------------------------------- delay and wait_for_event

def test_delay_is_a_future_run_at_and_workers_sleep_until_it(db, dsn, handlers, engine):
    rec = Record()
    handlers["record"] = rec
    name = make_workflow(db, {"start_at": "first", "steps": {
        "first": action("record", nxt="pause"),
        "pause": {"type": "delay", "duration_seconds": 1, "next": "second"},
        "second": action("record")}})
    iid = engine.start_workflow(name, {})
    with Pool(dsn, handlers, max_sleep=5.0):
        wait_until(terminal(db, iid))
    gap = rec.times[1] - rec.times[0]
    assert 1.0 <= gap < 2.0, gap
    assert instance(db, iid)["status"] == "completed"


def test_wait_for_event_resumes_when_the_event_arrives(db, dsn, handlers, engine):
    handlers["record"] = Record()
    name = make_workflow(db, {"start_at": "w", "steps": {
        "w": {"type": "wait_for_event", "timeout_seconds": 60, "next": "after"},
        "after": action("record")}})
    iid = engine.start_workflow(name, {})
    with Pool(dsn, handlers):
        wait_until(lambda: [e for e in executions(db, iid) if e["status"] == "running"])
        engine.send_event(iid, {"approved": True})
        wait_until(terminal(db, iid))
    row = instance(db, iid)
    assert row["status"] == "completed" and row["data"]["approved"] is True
    assert [j["status"] for j in jobs(db, iid) if j["kind"] == "wait_timeout"] == ["cancelled"]


def test_wait_for_event_times_out_and_fails(db, dsn, handlers, engine):
    name = make_workflow(db, {"start_at": "w", "steps": {
        "w": {"type": "wait_for_event", "timeout_seconds": 1, "next": "end"}}})
    iid = engine.start_workflow(name, {})
    with Pool(dsn, handlers):
        wait_until(terminal(db, iid))
    assert instance(db, iid)["status"] == "failed"
    assert "timed out" in executions(db, iid)[0]["error_details"]


def test_send_event_to_an_instance_that_is_not_waiting_is_rejected(db, engine):
    handlers_ = {"record": Record()}
    name = make_workflow(db, {"start_at": "a", "steps": {"a": action("record")}})
    iid = engine.start_workflow(name, {})
    with pytest.raises(pg_engine.StateError):
        engine.send_event(iid, {})


# ---------------------------------------------------------------- crash safety (what the sweeper and late-ack do today)

def test_job_of_a_crashed_worker_is_reclaimed_after_the_lease_expires(db, dsn, handlers):
    rec = Record()
    handlers["record"] = rec
    name = make_workflow(db, {"start_at": "a", "steps": {"a": action("record")}})
    crashed = Engine(dsn, handlers, worker_id="crashed", lease_seconds=0.3)
    survivor = Engine(dsn, handlers, worker_id="survivor", lease_seconds=30)
    try:
        iid = survivor.start_workflow(name, {})
        assert crashed.claim() is not None            # takes the job, then "dies" without finishing
        assert survivor.run_once() is False           # lease still valid: nothing for anyone else
        time.sleep(0.5)
        assert survivor.run_once() is True            # lease expired: reclaimed and executed
    finally:
        crashed.close(); survivor.close()
    assert instance(db, iid)["status"] == "completed"
    assert rec.calls == 1
    assert jobs(db, iid)[0]["claims"] == 2


def test_stale_worker_result_is_discarded_after_its_job_was_reclaimed(db, dsn, handlers):
    """At-least-once: the handler runs twice, but state advances exactly once."""
    rec = Record(sleep=1.2, slow_first_call_only=True)
    after = Record()
    handlers["slow_once"], handlers["after"] = rec, after
    name = make_workflow(db, {"start_at": "a", "steps": {"a": action("slow_once", nxt="b"), "b": action("after")}})
    a = Engine(dsn, handlers, worker_id="A", lease_seconds=0.4)
    b = Engine(dsn, handlers, worker_id="B", lease_seconds=30)
    try:
        iid = b.start_workflow(name, {})
        t = threading.Thread(target=a.run_once)
        t.start()                                     # A claims, handler sleeps past its lease
        time.sleep(0.7)
        while b.run_once():                           # B reclaims step a (fast now) and carries on to step b
            pass
        t.join(timeout=10)                            # A finally returns: its result must be discarded
    finally:
        a.close(); b.close()
    assert instance(db, iid)["status"] == "completed"
    assert rec.calls == 2 and after.calls == 1        # side effect repeated once, next step NOT run twice
    done = [e["step_name"] for e in executions(db, iid) if e["status"] == "completed"]
    assert done == ["a", "b"]
    assert [e["error_details"] for e in executions(db, iid) if e["status"] == "failed"] == ["worker lost (lease expired)"]


def test_a_step_that_keeps_killing_its_worker_is_marked_dead(db, dsn, handlers, monkeypatch):
    monkeypatch.setattr(pg_engine, "MAX_CLAIMS", 2)
    handlers["record"] = Record()
    name = make_workflow(db, {"start_at": "a", "steps": {"a": action("record")}})
    e = Engine(dsn, handlers, lease_seconds=0.05)
    try:
        iid = e.start_workflow(name, {})
        for _ in range(2):                            # MAX_CLAIMS claims that never finish
            assert e.claim() is not None
            time.sleep(0.1)
        assert e.claim() == {"poison": True}          # the next claim exceeds MAX_CLAIMS and kills the job
        assert e.claim() is None
    finally:
        e.close()
    assert instance(db, iid)["status"] == "failed"
    assert jobs(db, iid)[0]["status"] == "dead"


# ---------------------------------------------------------------- cancel (F-17)

def test_cancel_during_a_running_step_discards_the_result_and_stops_the_workflow(db, dsn, handlers, engine):
    slow = Record(sleep=0.8, set_data={"marker": "should-not-appear"})
    nxt = Record()
    handlers["slow"], handlers["nxt"] = slow, nxt
    name = make_workflow(db, {"start_at": "a", "steps": {"a": action("slow", nxt="b"), "b": action("nxt")}})
    worker = Engine(dsn, handlers)
    try:
        iid = engine.start_workflow(name, {})
        t = threading.Thread(target=worker.run_once)
        t.start()
        wait_until(lambda: slow.calls == 1)
        engine.cancel_instance(iid)
        t.join(timeout=10)
    finally:
        worker.close()
    row = instance(db, iid)
    assert row["status"] == "cancelled"
    assert "marker" not in row["data"]
    assert nxt.calls == 0
    assert not [j for j in jobs(db, iid) if j["status"] == "queued"]


# ---------------------------------------------------------------- concurrency and a rough throughput number

def test_many_instances_across_workers_run_every_step_exactly_once(db, dsn, handlers, engine):
    name = make_workflow(db, {"start_at": "a", "steps": {
        "a": {"type": "action", "connector_id": "internal", "action_id": "transform_data",
              "config": {"set": {"a": 1}}, "next": "b"},
        "b": {"type": "action", "connector_id": "internal", "action_id": "log",
              "config": {"message": "n={{a}}"}, "next": "c"},
        "c": {"type": "action", "connector_id": "internal", "action_id": "transform_data",
              "config": {"set": {"c": 3}}, "next": "end"}}})
    n, workers = int(os.environ.get("SPIKE_INSTANCES", 300)), int(os.environ.get("SPIKE_WORKERS", 4))
    ids = [engine.start_workflow(name, {}) for _ in range(n)]
    started = time.monotonic()
    with Pool(dsn, handlers, n=workers, max_sleep=0.2):
        cur = db.cursor()
        wait_until(lambda: (cur.execute("SELECT count(*) AS c FROM workflow_instances WHERE status = 'completed'") or cur.fetchone()["c"]) == n,
                   timeout=120, interval=0.1)
    elapsed = time.monotonic() - started
    cur = db.cursor()
    cur.execute("SELECT step_name, count(*) AS c FROM workflow_step_executions WHERE status = 'completed' GROUP BY step_name")
    assert {r["step_name"]: r["c"] for r in cur.fetchall()} == {"a": n, "b": n, "c": n}
    cur.execute("SELECT count(*) AS c FROM jobs WHERE status <> 'done'")
    assert cur.fetchone()["c"] == 0
    print(f"\n[throughput] {n} instances x 3 steps with {workers} worker threads: {elapsed:.1f}s "
          f"= {n / elapsed:.0f} instances/s, {3 * n / elapsed:.0f} steps/s (one laptop, Docker Desktop, Python threads)")
