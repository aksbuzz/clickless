"""The worker process loop: wake-ups, parallelism and shutdown."""
import threading
import time

import pytest

from src.engine.worker import Worker
from tests.integration.helpers import Record, action, instance, make_workflow, running_worker, start, terminal, wait_until


@pytest.fixture
def handlers():
    return {}


def test_a_new_job_wakes_an_idle_worker_without_waiting_for_the_poll(conn, handlers):
    handlers["record"] = Record()
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("record")}})
    with running_worker(handlers, idle_poll=60.0):
        time.sleep(0.5)                              # let the worker go idle
        started = time.monotonic()
        iid = start(name, {})
        wait_until(terminal(conn, iid), timeout=5)
        assert time.monotonic() - started < 2.0      # LISTEN/NOTIFY, not the 60 s fallback


def test_handlers_run_in_parallel_up_to_the_concurrency(conn, handlers):
    handlers["slow"] = Record(sleep=0.5)
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("slow")}})
    ids = [start(name, {}) for _ in range(8)]
    started = time.monotonic()
    with running_worker(handlers, concurrency=8, idle_poll=0.5):
        for iid in ids:
            wait_until(terminal(conn, iid), timeout=20)
    assert time.monotonic() - started < 3.0         # one at a time would take 4 s
    assert all(instance(conn, i)["status"] == "completed" for i in ids)


def test_concurrency_is_a_limit(conn, handlers):
    seen = {"now": 0, "max": 0}
    lock = threading.Lock()

    class Gauge:
        def execute(self, instance_id, data, config=None, **kwargs):
            from src.worker.models import ActionResult, ActionStatus
            with lock:
                seen["now"] += 1
                seen["max"] = max(seen["max"], seen["now"])
            time.sleep(0.2)
            with lock:
                seen["now"] -= 1
            return ActionResult(ActionStatus.SUCCESS, data)

    handlers["gauge"] = Gauge()
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("gauge")}})
    ids = [start(name, {}) for _ in range(10)]
    with running_worker(handlers, concurrency=3, idle_poll=0.5):
        for iid in ids:
            wait_until(terminal(conn, iid), timeout=20)
    assert seen["max"] == 3


def test_stopping_the_worker_returns_promptly_even_when_idle(conn, handlers):
    worker = Worker(handlers, concurrency=3, lease_seconds=30, idle_poll=60.0)
    stop = threading.Event()
    thread = threading.Thread(target=worker.run, args=(stop,), daemon=True)
    thread.start()
    time.sleep(0.5)
    started = time.monotonic()
    stop.set()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert time.monotonic() - started < 3.0


def test_the_worker_finishes_the_step_in_flight_before_it_stops(conn, handlers):
    rec = Record(sleep=0.8)
    handlers["slow"] = rec
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("slow")}})
    iid = start(name, {})
    worker = Worker(handlers, concurrency=1, lease_seconds=30, idle_poll=0.5)
    stop = threading.Event()
    thread = threading.Thread(target=worker.run, args=(stop,), daemon=True)
    thread.start()
    wait_until(lambda: rec.calls == 1)
    stop.set()                                       # shutdown requested while the handler is running
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert instance(conn, iid)["status"] == "completed"
