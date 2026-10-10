"""Spike: a Postgres-only runtime for the workflow engine.

One job = one step. A worker claims a due job (FOR UPDATE SKIP LOCKED, with a lease), runs the step,
and in ONE transaction saves the result, advances the instance and enqueues the next job.

What this replaces from the current design: outbox + relay, RabbitMQ, Celery acks and DLQs,
the engine/worker split, the Redis instance lock, the stale-event guards and the recovery sweeper.

It is a spike: no HTTP layer, no metrics, no purge of finished jobs, no lease heartbeat.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import select
import socket
import threading
import uuid
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from src.shared.connectors.template import resolve_config

log = logging.getLogger("pg_engine")

LEASE_SECONDS = 300      # matches the current Celery hard time limit
MAX_CLAIMS = 5           # a job taken this many times without finishing is marked dead
MAX_INLINE_STEPS = 100   # bound on branch/delay hops resolved inside one transaction (cycle guard)
NOTIFY_CHANNEL = "jobs_ready"
TERMINAL = ("completed", "failed", "cancelled")


class StateError(Exception):
    pass


def dumps(obj) -> str:
    return json.dumps(obj, default=str)


def resolve_field(data, path):
    current = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def evaluate_condition(data: dict, condition: dict) -> bool:
    """Same operators as OrchestrationService._evaluate_condition."""
    actual = resolve_field(data, condition.get("field", ""))
    op, expected = condition.get("operator", "eq"), condition.get("value")
    if op == "eq": return actual == expected
    if op == "neq": return actual != expected
    if op == "gt": return actual is not None and actual > expected
    if op == "gte": return actual is not None and actual >= expected
    if op == "lt": return actual is not None and actual < expected
    if op == "lte": return actual is not None and actual <= expected
    if op == "contains": return actual is not None and expected in actual
    if op == "exists": return actual is not None
    return False


class Engine:
    """One Engine per thread (it owns one DB connection)."""

    def __init__(self, dsn: str, handlers: dict, worker_id: str | None = None, lease_seconds: float = LEASE_SECONDS):
        self.dsn = dsn
        self.conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
        self.handlers = handlers
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.lease = lease_seconds

    def close(self):
        self.conn.close()

    @contextmanager
    def tx(self):
        try:
            with self.conn.cursor() as cur:
                yield cur
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise

    # ------------------------------------------------------------------ public API (what the HTTP layer would call)

    def start_workflow(self, name: str, data: dict) -> str:
        with self.tx() as cur:
            cur.execute(
                "SELECT v.id, v.definition FROM workflow_versions v JOIN workflows w ON w.id = v.workflow_id "
                "WHERE w.name = %s AND v.is_active", (name,))
            row = cur.fetchone()
            if not row:
                raise LookupError(f"workflow '{name}' not found")
            cur.execute(
                "INSERT INTO workflow_instances (workflow_version_id, status, data) VALUES (%s, 'pending', %s) RETURNING id",
                (row["id"], dumps(data)))
            instance_id = str(cur.fetchone()["id"])
            self._enqueue(cur, instance_id, row["definition"]["start_at"])
            return instance_id

    def cancel_instance(self, instance_id: str) -> None:
        with self.tx() as cur:
            inst = self._lock_instance(cur, instance_id)
            if inst is None:
                raise LookupError("instance not found")
            if inst["status"] in TERMINAL:
                raise StateError(f"cannot cancel instance with status '{inst['status']}'")
            cur.execute("UPDATE workflow_instances SET status = 'cancelled' WHERE id = %s", (instance_id,))
            cur.execute("UPDATE jobs SET status = 'cancelled', finished_at = now() "
                        "WHERE instance_id = %s AND status = 'queued'", (instance_id,))

    def send_event(self, instance_id: str, data: dict) -> None:
        with self.tx() as cur:
            inst = self._lock_instance(cur, instance_id)
            if inst is None:
                raise LookupError("instance not found")
            step = inst["current_step"]
            sdef = inst["definition"].get("steps", {}).get(step or "", {})
            if inst["status"] != "running" or sdef.get("type") != "wait_for_event":
                raise StateError("instance is not waiting for an event")
            cur.execute(
                "SELECT id FROM workflow_step_executions WHERE instance_id = %s AND step_name = %s AND status = 'running' "
                "ORDER BY started_at DESC LIMIT 1", (instance_id, step))
            execution = cur.fetchone()
            if not execution:
                raise StateError("wait step is not armed yet, retry shortly")
            merged = dict(inst["data"] or {})
            merged.update(data)
            cur.execute("UPDATE workflow_instances SET data = %s WHERE id = %s", (dumps(merged), instance_id))
            cur.execute("UPDATE workflow_step_executions SET status = 'completed', completed_at = now(), output_data = %s "
                        "WHERE id = %s", (dumps(data), execution["id"]))
            cur.execute("UPDATE jobs SET status = 'cancelled', finished_at = now() "
                        "WHERE instance_id = %s AND kind = 'wait_timeout' AND status = 'queued'", (instance_id,))
            inst["data"] = merged
            self._advance_to(cur, inst, sdef.get("next"), 0.0)

    # ------------------------------------------------------------------ worker loop

    def run_forever(self, stop: threading.Event, max_sleep: float = 5.0) -> None:
        """Drain due jobs, then sleep until a NOTIFY arrives or the next job is due (never longer than max_sleep)."""
        listener = psycopg2.connect(self.dsn)
        listener.autocommit = True
        listener.cursor().execute(f"LISTEN {NOTIFY_CHANNEL}")
        try:
            while not stop.is_set():
                while not stop.is_set() and self.run_once():
                    pass
                wait = min(self._seconds_until_next_job(max_sleep), max_sleep)
                if select.select([listener], [], [], wait)[0]:
                    listener.poll()
                    del listener.notifies[:]
        finally:
            listener.close()

    def run_once(self) -> bool:
        """Claim and execute one job. Returns False when nothing was due."""
        job = self.claim()
        if job is None:
            return False
        if job.get("poison"):
            return True
        try:
            self._execute(job)
        except Exception:
            log.exception("engine error on job %s; releasing it for a later retry", job["id"])
            self._release(job)
        return True

    def claim(self) -> dict | None:
        with self.tx() as cur:
            cur.execute(
                """
                UPDATE jobs SET status = 'running', locked_by = %s,
                                locked_until = now() + make_interval(secs => %s), claims = claims + 1
                WHERE id = (
                    SELECT id FROM jobs
                    WHERE (status = 'queued' AND run_at <= now())
                       OR (status = 'running' AND locked_until < now())
                    ORDER BY run_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1)
                RETURNING *
                """, (self.worker_id, self.lease))
            job = cur.fetchone()
            if job is None:
                return None
            if job["claims"] > MAX_CLAIMS:
                message = f"job claimed {job['claims']} times without finishing (does the step kill its worker?)"
                inst = self._lock_instance(cur, str(job["instance_id"]))
                if inst and inst["status"] not in TERMINAL:
                    self._fail_instance(cur, inst, job["step_name"], message)
                self._finish_job(cur, job, "dead", message)
                return {"poison": True}
            return job

    # ------------------------------------------------------------------ executing a job

    def _execute(self, job: dict) -> None:
        work = self._begin(job)
        if work is None:
            return
        outcome = self._run_handler(work)
        self._finish(job, work, outcome)

    def _begin(self, job: dict) -> dict | None:
        """Short transaction before the handler runs. Returns None when the job needed no handler."""
        instance_id, step = str(job["instance_id"]), job["step_name"]
        with self.tx() as cur:
            inst = self._lock_instance(cur, instance_id)
            if inst is None or inst["status"] in TERMINAL:
                self._finish_job(cur, job, "done")
                return None
            if job["kind"] == "wait_timeout":
                self._on_wait_timeout(cur, job, inst)
                return None
            if step == "end":
                self._complete_instance(cur, inst)
                self._finish_job(cur, job, "done")
                return None
            sdef = inst["definition"].get("steps", {}).get(step)
            if sdef is None:
                message = f"step '{step}' is not defined in the workflow"
                self._fail_instance(cur, inst, step, message)
                self._finish_job(cur, job, "dead", message)
                return None
            stype = sdef.get("type", "action")
            if stype == "branch" or stype == "delay" or "duration_seconds" in sdef:
                self._advance_to(cur, inst, step, 0.0)
                self._finish_job(cur, job, "done")
                return None

            cur.execute("UPDATE workflow_instances SET status = 'running', current_step = %s, current_step_attempts = %s "
                        "WHERE id = %s", (step, job["attempts"] + 1, instance_id))
            # an execution left 'running' by a worker that died is closed here
            cur.execute("UPDATE workflow_step_executions SET status = 'failed', completed_at = now(), "
                        "error_details = 'worker lost (lease expired)' "
                        "WHERE instance_id = %s AND step_name = %s AND status = 'running'", (instance_id, step))

            if stype == "wait_for_event":
                self._insert_execution(cur, instance_id, step, 1)
                timeout = sdef.get("timeout_seconds")
                if timeout:
                    self._enqueue(cur, instance_id, step, float(timeout), kind="wait_timeout")
                self._finish_job(cur, job, "done")
                return None

            config, pre_error = dict(sdef.get("config", {})), None
            connection_id = sdef.get("connection_id")
            if connection_id:
                cur.execute("SELECT config FROM connections WHERE id = %s", (connection_id,))
                row = cur.fetchone()
                if row and row["config"]:
                    merged = dict(row["config"])
                    merged.update(config)
                    config = merged
                else:
                    pre_error = f"connection '{connection_id}' not found"
            exec_id = self._insert_execution(cur, instance_id, step, job["attempts"] + 1)
            return {"instance_id": instance_id, "step": step, "sdef": sdef, "exec_id": exec_id,
                    "data": inst["data"] or {}, "config": config, "pre_error": pre_error}

    def _run_handler(self, work: dict) -> tuple[bool, dict | None, str | None]:
        """Runs with NO transaction open (the current design holds one for the whole handler call)."""
        if work["pre_error"]:
            return False, None, work["pre_error"]
        action_id = work["sdef"].get("action_id", work["step"])
        handler = self.handlers.get(action_id)
        if handler is None:
            return False, None, f"no handler registered for action '{action_id}'"
        try:
            config = resolve_config(work["config"], work["data"])   # templating in ONE place (F-09)
            result = handler.execute(work["instance_id"], copy.deepcopy(work["data"]), config=config, task_context=None)
            return result.status.value == "success", result.updated_data, result.error_message
        except Exception as exc:
            return False, None, f"{type(exc).__name__}: {exc}"

    def _finish(self, job: dict, work: dict, outcome: tuple) -> None:
        """One transaction: fence, save result, advance, enqueue next."""
        ok, new_data, error = outcome
        instance_id, step, sdef, exec_id = work["instance_id"], work["step"], work["sdef"], work["exec_id"]
        with self.tx() as cur:
            inst = self._lock_instance(cur, instance_id)
            cur.execute("SELECT status, locked_by FROM jobs WHERE id = %s FOR UPDATE", (job["id"],))
            current = cur.fetchone()
            if not current or current["status"] != "running" or current["locked_by"] != self.worker_id:
                log.warning("lease lost for job %s, discarding the result", job["id"])
                return
            if inst is None or inst["status"] in TERMINAL or inst["current_step"] != step:
                cur.execute("UPDATE workflow_step_executions SET status = 'failed', completed_at = now(), "
                            "error_details = 'instance cancelled or moved on, result discarded' WHERE id = %s", (exec_id,))
                self._finish_job(cur, job, "done")
                return

            if ok:
                data_in = work["data"]
                new_data = data_in if new_data is None else new_data
                delta = {k: v for k, v in new_data.items() if k not in data_in or data_in[k] != v}
                removed = [k for k in data_in if k not in new_data]
                data = dict(inst["data"] or {})
                data.update(delta)
                for key in removed:
                    data.pop(key, None)
                cur.execute("UPDATE workflow_instances SET data = %s WHERE id = %s", (dumps(data), instance_id))
                cur.execute("UPDATE workflow_step_executions SET status = 'completed', completed_at = now(), "
                            "output_data = %s WHERE id = %s", (dumps(delta), exec_id))   # only what the step changed
                inst["data"] = data
                self._finish_job(cur, job, "done")
                self._advance_to(cur, inst, sdef.get("next"), 0.0)
                return

            retry = sdef.get("retry") or {}
            max_attempts, delay = int(retry.get("max_attempts", 1)), int(retry.get("delay_seconds", 5))
            attempts = job["attempts"] + 1
            cur.execute("UPDATE workflow_step_executions SET status = 'failed', completed_at = now(), error_details = %s "
                        "WHERE id = %s", (error, exec_id))
            if attempts < max_attempts:
                cur.execute("UPDATE jobs SET status = 'queued', attempts = %s, claims = 0, locked_by = NULL, "
                            "locked_until = NULL, run_at = now() + make_interval(secs => %s), last_error = %s WHERE id = %s",
                            (attempts, delay, error, job["id"]))
                cur.execute("SELECT pg_notify(%s, '')", (NOTIFY_CHANNEL,))
            else:
                self._finish_job(cur, job, "dead", error)
                self._fail_instance(cur, inst, step, error, record=False)

    # ------------------------------------------------------------------ state transitions

    def _advance_to(self, cur, inst: dict, name: str | None, offset: float) -> None:
        """Move the instance to step `name`. Branch and delay steps are resolved inline; the first
        action or wait step becomes a job (run_at is pushed out by any delays passed on the way)."""
        steps, data, instance_id = inst["definition"].get("steps", {}), inst["data"] or {}, str(inst["id"])
        for _ in range(MAX_INLINE_STEPS):
            if name in (None, "end"):
                if offset > 0:
                    self._enqueue_step(cur, instance_id, "end", offset)
                else:
                    self._complete_instance(cur, inst)
                return
            sdef = steps.get(name)
            if sdef is None:
                self._fail_instance(cur, inst, name, f"step '{name}' is not defined in the workflow")
                return
            stype = sdef.get("type", "action")
            if stype == "branch":
                result = evaluate_condition(data, sdef.get("condition", {}))
                target = sdef.get("on_true") if result else sdef.get("on_false")
                self._record_control(cur, instance_id, name, {"branch_result": result, "next_step": target})
                name = target
            elif stype == "delay" or "duration_seconds" in sdef:
                seconds = int(sdef.get("duration_seconds", 60))
                self._record_control(cur, instance_id, name, {"delay_seconds": seconds})
                offset += seconds
                name = sdef.get("next")
            else:
                self._enqueue_step(cur, instance_id, name, offset)
                return
        self._fail_instance(cur, inst, name or "end",
                            f"more than {MAX_INLINE_STEPS} branch/delay steps in a row (cycle in the definition?)")

    def _enqueue_step(self, cur, instance_id: str, name: str, offset: float) -> None:
        cur.execute("UPDATE workflow_instances SET status = 'running', current_step = %s, current_step_attempts = 0 "
                    "WHERE id = %s", (name, instance_id))
        self._enqueue(cur, instance_id, name, offset)

    def _enqueue(self, cur, instance_id: str, step: str, offset: float = 0.0, kind: str = "run_step") -> None:
        cur.execute("INSERT INTO jobs (instance_id, step_name, kind, run_at) "
                    "VALUES (%s, %s, %s, now() + make_interval(secs => %s))", (instance_id, step, kind, offset))
        cur.execute("SELECT pg_notify(%s, '')", (NOTIFY_CHANNEL,))   # delivered when this transaction commits

    def _on_wait_timeout(self, cur, job: dict, inst: dict) -> None:
        instance_id, step = str(inst["id"]), job["step_name"]
        cur.execute("SELECT id FROM workflow_step_executions WHERE instance_id = %s AND step_name = %s AND status = 'running'",
                    (instance_id, step))
        waiting = cur.fetchone()
        if inst["current_step"] == step and inst["status"] == "running" and waiting:
            message = f"wait step '{step}' timed out"
            cur.execute("UPDATE workflow_step_executions SET status = 'failed', completed_at = now(), error_details = %s "
                        "WHERE id = %s", (message, waiting["id"]))
            self._fail_instance(cur, inst, step, message, record=False)
        self._finish_job(cur, job, "done")

    def _lock_instance(self, cur, instance_id: str) -> dict | None:
        cur.execute(
            "SELECT i.id, i.status, i.current_step, i.data, v.definition "
            "FROM workflow_instances i JOIN workflow_versions v ON v.id = i.workflow_version_id "
            "WHERE i.id = %s FOR UPDATE OF i", (instance_id,))
        return cur.fetchone()

    def _insert_execution(self, cur, instance_id: str, step: str, attempt: int) -> str:
        cur.execute("INSERT INTO workflow_step_executions (instance_id, step_name, status, attempts, started_at) "
                    "VALUES (%s, %s, 'running', %s, now()) RETURNING id", (instance_id, step, attempt))
        return str(cur.fetchone()["id"])

    def _record_control(self, cur, instance_id: str, step: str, output: dict) -> None:
        cur.execute("INSERT INTO workflow_step_executions (instance_id, step_name, status, attempts, started_at, "
                    "completed_at, output_data) VALUES (%s, %s, 'completed', 1, now(), now(), %s)",
                    (instance_id, step, dumps(output)))

    def _complete_instance(self, cur, inst: dict) -> None:
        cur.execute("UPDATE workflow_instances SET status = 'completed', current_step = NULL WHERE id = %s", (str(inst["id"]),))

    def _fail_instance(self, cur, inst: dict, step: str, message: str, record: bool = True) -> None:
        instance_id = str(inst["id"])
        cur.execute("UPDATE workflow_instances SET status = 'failed' WHERE id = %s", (instance_id,))
        if record:
            cur.execute("INSERT INTO workflow_step_executions (instance_id, step_name, status, attempts, started_at, "
                        "completed_at, error_details) VALUES (%s, %s, 'failed', 1, now(), now(), %s)",
                        (instance_id, step, message))

    def _finish_job(self, cur, job: dict, status: str, error: str | None = None) -> None:
        cur.execute("UPDATE jobs SET status = %s, finished_at = now(), last_error = COALESCE(%s, last_error) WHERE id = %s",
                    (status, error, job["id"]))

    def _release(self, job: dict) -> None:
        with self.tx() as cur:
            cur.execute("UPDATE jobs SET status = 'queued', locked_by = NULL, locked_until = NULL, "
                        "run_at = now() + interval '10 seconds' WHERE id = %s AND locked_by = %s", (job["id"], self.worker_id))

    def _seconds_until_next_job(self, cap: float) -> float:
        with self.tx() as cur:
            cur.execute(
                "SELECT EXTRACT(EPOCH FROM (LEAST((SELECT min(run_at) FROM jobs WHERE status = 'queued'), "
                "(SELECT min(locked_until) FROM jobs WHERE status = 'running')) - now())) AS s")
            seconds = cur.fetchone()["s"]
        return cap if seconds is None else max(0.0, min(float(seconds), cap))
