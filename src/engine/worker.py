"""Worker threads: claim a job, run its step with no transaction open, record the result.

One process runs `concurrency` runner threads that share a small connection pool, plus one dispatcher thread
that holds the single LISTEN connection. The dispatcher wakes a runner when a job is queued or comes due. A
runner that has just finished a job wakes one more, so a burst of jobs spreads across idle threads without every
thread polling.
"""
import copy
import os
import select
import socket
import threading
import time
import uuid
from typing import Dict

import psycopg2
import structlog

from src.engine import runtime
from src.engine.runtime import NOTIFY_CHANNEL, StepOutcome, StepWork
from src.engine.steps import resolve_step_config
from src.shared.db import db_cursor, get_connection_string
from src.shared.logging_config import log


class WakeSignal:
    """Hands wake-ups to waiting threads without losing any. Tokens are capped so a quiet period cannot store up
    an unbounded number of spurious wake-ups."""

    def __init__(self, cap: int = 64):
        self._cond = threading.Condition()
        self._tokens = 0
        self._cap = cap

    def wake(self, count: int = 1) -> None:
        with self._cond:
            self._tokens = min(self._tokens + count, self._cap)
            self._cond.notify(count)

    def wait(self, timeout: float) -> bool:
        """True if a wake-up was consumed, False if the timeout passed first."""
        with self._cond:
            if self._tokens == 0:
                self._cond.wait(timeout)
            if self._tokens > 0:
                self._tokens -= 1
                return True
            return False


def execute_step(work: StepWork, handlers: Dict[str, object]) -> StepOutcome:
    """Run the handler for a step. Never raises: every problem becomes a failed outcome with a reason."""
    if work.pre_error:
        return StepOutcome(False, error=work.pre_error)
    handler = handlers.get(work.action_id)
    if handler is None:
        return StepOutcome(False, error=f"no handler registered for action '{work.action_id}'")
    try:
        # Templates are resolved here, once, for every handler. A handler can name keys that must stay as written.
        config = resolve_step_config(work.config, work.data, getattr(handler, "untemplated_keys", ()))
        result = handler.execute(work.instance_id, copy.deepcopy(work.data), config=config)
        return StepOutcome(result.status.value == "success", result.updated_data, result.error_message)
    except Exception as exc:
        log.error("Action handler raised", action=work.action_id, instance_id=work.instance_id, exc_info=True)
        return StepOutcome(False, error=f"{type(exc).__name__}: {exc}")


class StepRunner:
    """Runs one job at a time. Not thread-safe: use one per thread."""

    def __init__(self, handlers: Dict[str, object], worker_id: str = None, lease_seconds: float = 300.0):
        self.handlers = handlers
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.lease_seconds = lease_seconds

    def run_one(self) -> bool:
        """Claim and execute one job. Returns False when nothing was due."""
        with db_cursor() as cur:
            job = runtime.claim_job(cur, self.worker_id, self.lease_seconds)
        if job is None:
            return False
        if job.get("poison"):
            return True
        try:
            with db_cursor() as cur:
                work = runtime.begin_step(cur, job)
            if work is None:
                return True
            structlog.contextvars.bind_contextvars(
                instance_id=work.instance_id, step=work.step, **({"request_id": work.request_id} if work.request_id else {}))
            outcome = execute_step(work, self.handlers)
            with db_cursor() as cur:
                runtime.finish_step(cur, job, work, outcome, self.worker_id)
        except Exception:
            log.error("Engine error on a job; releasing it for a later retry", job_id=job["id"], exc_info=True)
            self._release(job)
        finally:
            structlog.contextvars.clear_contextvars()
        return True

    def _release(self, job: dict) -> None:
        try:
            with db_cursor() as cur:
                runtime.release_job(cur, job, self.worker_id)
        except Exception:
            log.error("Could not release a job; its lease will expire", job_id=job["id"], exc_info=True)


class Worker:
    def __init__(self, handlers: Dict[str, object], concurrency: int = 8, lease_seconds: float = 300.0,
                 idle_poll: float = 5.0, shutdown_grace: float = 60.0):
        self.handlers = handlers
        self.concurrency = concurrency
        self.lease_seconds = lease_seconds
        self.idle_poll = idle_poll
        self.shutdown_grace = shutdown_grace
        self.signal = WakeSignal(cap=concurrency)

    def run(self, stop: threading.Event) -> None:
        """Run until `stop` is set, then let every step in flight finish."""
        runners = [threading.Thread(target=self._runner_loop, args=(stop,), name=f"step-runner-{i}", daemon=True)
                   for i in range(self.concurrency)]
        dispatcher = threading.Thread(target=self._dispatch_loop, args=(stop,), name="dispatcher", daemon=True)
        for thread in [dispatcher, *runners]:
            thread.start()
        stop.wait()
        self.signal.wake(self.concurrency)
        deadline = time.monotonic() + self.shutdown_grace
        for thread in [*runners, dispatcher]:
            thread.join(timeout=max(0.1, deadline - time.monotonic()))
            if thread.is_alive():
                log.warning("A worker thread did not stop in time; its job's lease will expire", thread=thread.name)

    def _runner_loop(self, stop: threading.Event) -> None:
        runner = StepRunner(self.handlers, lease_seconds=self.lease_seconds)
        while not stop.is_set():
            try:
                worked = runner.run_one()
            except Exception:
                log.error("Worker loop error (is the database reachable?)", exc_info=True)
                stop.wait(1.0)
                continue
            if worked:
                self.signal.wake(1)       # let an idle thread check for more work
                continue
            self.signal.wait(timeout=self.idle_poll)

    def _dispatch_loop(self, stop: threading.Event) -> None:
        conn = None
        next_safety_wake = time.monotonic() + self.idle_poll
        while not stop.is_set():
            try:
                if conn is None:
                    conn = self._listen()
                with db_cursor() as cur:
                    due_in = runtime.seconds_until_next_job(cur, self.idle_poll)
                wait = min(max(due_in + 0.01, 0.05), 1.0)      # at most 1 s so a stop request is noticed
                if select.select([conn], [], [], wait)[0]:
                    conn.poll()
                    count = len(conn.notifies)
                    del conn.notifies[:]
                    self.signal.wake(max(1, min(count, self.concurrency)))
                elif due_in <= wait:
                    self.signal.wake(1)                         # a job came due, or a lease expired
                if time.monotonic() >= next_safety_wake:
                    self.signal.wake(1)                         # safety net against a missed notification
                    next_safety_wake = time.monotonic() + self.idle_poll
            except Exception:
                log.error("Dispatcher error; reconnecting", exc_info=True)
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = None
                stop.wait(1.0)
        if conn is not None:
            conn.close()

    @staticmethod
    def _listen():
        conn = psycopg2.connect(get_connection_string())
        conn.autocommit = True
        conn.cursor().execute(f"LISTEN {NOTIFY_CHANNEL}")
        return conn
