"""Helpers shared by the engine integration tests."""
import json
import threading
import time
import uuid
from contextlib import contextmanager

from src.engine.worker import Worker
from src.shared.db import db_cursor
from src.worker.models import ActionResult, ActionStatus

TERMINAL = ("completed", "failed", "cancelled")


class Record:
    """A handler that records its calls and can fail, sleep or add data."""

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


@contextmanager
def running_worker(handlers, concurrency=2, lease_seconds=30, idle_poll=5.0):
    worker = Worker(handlers, concurrency=concurrency, lease_seconds=lease_seconds, idle_poll=idle_poll)
    stop = threading.Event()
    thread = threading.Thread(target=worker.run, args=(stop,), daemon=True)
    thread.start()
    try:
        yield worker
    finally:
        stop.set()
        thread.join(timeout=15)
        assert not thread.is_alive(), "the worker did not stop"


def make_workflow(conn, definition) -> str:
    name = f"it_{uuid.uuid4().hex[:10]}"
    cur = conn.cursor()
    cur.execute("INSERT INTO workflows (name) VALUES (%s) RETURNING id", (name,))
    workflow_id = cur.fetchone()["id"]
    cur.execute("INSERT INTO workflow_versions (workflow_id, version, definition) VALUES (%s, 1, %s)",
                (workflow_id, json.dumps(definition)))
    return name


def start(name, data, request_id=None) -> str:
    from src.engine import runtime
    with db_cursor() as cur:
        return runtime.start_instance(cur, name, data, request_id=request_id)


def instance(conn, instance_id):
    cur = conn.cursor()
    cur.execute("SELECT * FROM workflow_instances WHERE id = %s", (instance_id,))
    return cur.fetchone()


def executions(conn, instance_id):
    cur = conn.cursor()
    cur.execute("SELECT * FROM workflow_step_executions WHERE instance_id = %s ORDER BY started_at, id", (instance_id,))
    return cur.fetchall()


def jobs(conn, instance_id):
    cur = conn.cursor()
    cur.execute("SELECT * FROM jobs WHERE instance_id = %s ORDER BY id", (instance_id,))
    return cur.fetchall()


def wait_until(predicate, timeout=15.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError("condition not met in time")


def terminal(conn, instance_id):
    return lambda: instance(conn, instance_id)["status"] in TERMINAL


def action(name, nxt="end", **extra):
    return {"type": "action", "connector_id": "x", "action_id": name, "next": nxt, **extra}
