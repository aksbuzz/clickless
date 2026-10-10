"""The workflow runtime on PostgreSQL: the job queue and the state machine in one place.

One job runs one step of one instance. A worker claims a due job (FOR UPDATE SKIP LOCKED) and takes a lease on
it. It then runs the step with no transaction open, and in a single transaction saves the result, advances the
instance and enqueues the next job. A job whose lease expires is claimed again, so crashes need no separate
recovery process. See docs/adr/0017 and 0018.

Every function takes a cursor, so the caller decides what shares a transaction (the API starts several
instances in one). Control steps (branch, delay, end) are resolved inside the transaction that finishes the
previous step; only action and wait_for_event steps become jobs.
"""
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.engine.steps import evaluate_condition, retry_policy, step_kind
from src.shared.errors import InstanceNotFoundError, InvalidStateError, WorkflowNotFoundError
from src.shared.logging_config import log
from src.shared.metrics import (
    step_duration_seconds,
    step_execution_total,
    step_retry_total,
    workflow_completed_total,
    workflow_duration_seconds,
    workflow_errors_total,
    workflow_started_total,
)

MAX_CLAIMS = int(os.getenv("JOB_MAX_CLAIMS", "5"))    # a job taken this often without finishing is marked dead
MAX_INLINE_STEPS = 100                                # bound on branch/delay hops in one transaction (cycle guard)
NOTIFY_CHANNEL = "jobs_ready"
TERMINAL = ("completed", "failed", "cancelled")


@dataclass
class StepWork:
    """Everything the worker needs to run one step, captured by begin_step."""
    instance_id: str
    step: str
    step_def: Dict[str, Any]
    execution_id: str
    attempt: int
    data: Dict[str, Any]
    config: Dict[str, Any]
    request_id: Optional[str]
    workflow_name: str
    started: float                       # time.monotonic() when the step began
    pre_error: Optional[str] = None      # a problem found before running (for example a missing connection)

    @property
    def action_id(self) -> str:
        return self.step_def.get("action_id", self.step)


@dataclass
class StepOutcome:
    ok: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


def _dumps(value) -> str:
    return json.dumps(value, default=str)


# ------------------------------------------------------------------ what the API calls

def start_instance(cur, workflow_name: str, data: dict, request_id: Optional[str] = None) -> str:
    """Start the active version of a workflow by name. Returns the instance id."""
    cur.execute(
        "SELECT v.id, v.definition FROM workflow_versions v JOIN workflows w ON w.id = v.workflow_id "
        "WHERE w.name = %s AND v.is_active",
        (workflow_name,),
    )
    row = cur.fetchone()
    if not row:
        raise WorkflowNotFoundError("Workflow definition not found")
    return start_instance_for_version(cur, str(row["id"]), row["definition"].get("start_at"), data, request_id)


def start_instance_for_version(cur, version_id: str, start_at: Optional[str], data: dict,
                               request_id: Optional[str] = None) -> str:
    """Create an instance of a known version and queue its first step, in the caller's transaction."""
    cur.execute(
        "INSERT INTO workflow_instances (workflow_version_id, status, data, request_id) "
        "VALUES (%s, 'pending', %s, %s) RETURNING id",
        (version_id, _dumps(data), request_id),
    )
    instance_id = str(cur.fetchone()["id"])
    _enqueue(cur, instance_id, str(start_at))
    return instance_id


def cancel_instance(cur, instance_id: str) -> None:
    inst = _lock_instance(cur, instance_id)
    if inst is None:
        raise InstanceNotFoundError("Instance not found")
    if inst["status"] in TERMINAL:
        raise InvalidStateError(f"Cannot cancel instance with status '{inst['status']}'")
    cur.execute("UPDATE workflow_instances SET status = 'cancelled' WHERE id = %s", (instance_id,))
    cur.execute("DELETE FROM jobs WHERE instance_id = %s AND status = 'queued'", (instance_id,))
    # A job that is running right now finishes, finds the instance cancelled, and discards its result.


def send_event(cur, instance_id: str, data: dict) -> str:
    """Resume an instance that is waiting for an event. Returns the name of the step that was waiting."""
    inst = _lock_instance(cur, instance_id)
    if inst is None:
        raise InstanceNotFoundError("Instance not found")
    step = inst["current_step"]
    step_def = inst["definition"].get("steps", {}).get(step or "", {})
    if inst["status"] != "running" or not step or step_kind(step_def) != "wait_for_event":
        raise InvalidStateError(f"Instance is not waiting for an event (status: '{inst['status']}')")
    cur.execute(
        "SELECT id FROM workflow_step_executions WHERE instance_id = %s AND step_name = %s AND status = 'running' "
        "ORDER BY started_at DESC LIMIT 1",
        (instance_id, step),
    )
    execution = cur.fetchone()
    if not execution:
        raise InvalidStateError("The wait step is not armed yet; try again in a moment")
    merged = dict(inst["data"] or {})
    merged.update(data)
    cur.execute("UPDATE workflow_instances SET data = %s WHERE id = %s", (_dumps(merged), instance_id))
    cur.execute(
        "UPDATE workflow_step_executions SET status = 'completed', completed_at = now(), output_data = %s WHERE id = %s",
        (_dumps(data), execution["id"]),
    )
    cur.execute("DELETE FROM jobs WHERE instance_id = %s AND kind = 'wait_timeout' AND status = 'queued'", (instance_id,))
    inst["data"] = merged
    _advance_to(cur, inst, step_def.get("next"), 0.0)
    return step


# ------------------------------------------------------------------ what the worker calls

def claim_job(cur, worker_id: str, lease_seconds: float) -> Optional[dict]:
    """Take the next due job, or one whose lease has expired. None when nothing is due.

    Returns {"poison": True} when the job it took had been claimed too many times without finishing; that job
    and its instance are failed.
    """
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
        """,
        (worker_id, lease_seconds),
    )
    job = cur.fetchone()
    if job is None:
        return None
    if job["claims"] > MAX_CLAIMS:
        message = f"job claimed {job['claims']} times without finishing (does the step kill its worker?)"
        inst = _lock_instance(cur, str(job["instance_id"]))
        if inst and inst["status"] not in TERMINAL:
            _fail_instance(cur, inst, job["step_name"], message)
        _finish_job(cur, job, "dead", message)
        return {"poison": True}
    return job


def begin_step(cur, job: dict) -> Optional[StepWork]:
    """Short transaction before the handler runs. Returns None when the job needed no handler."""
    instance_id, step = str(job["instance_id"]), job["step_name"]
    inst = _lock_instance(cur, instance_id)
    if inst is None or inst["status"] in TERMINAL:
        _finish_job(cur, job, "done")
        return None
    if inst["status"] == "pending":
        workflow_started_total.labels(workflow_name=inst["workflow_name"]).inc()
    if job["kind"] == "wait_timeout":
        _on_wait_timeout(cur, job, inst)
        return None
    if step == "end":
        _complete_instance(cur, inst)
        _finish_job(cur, job, "done")
        return None

    step_def = inst["definition"].get("steps", {}).get(step)
    if step_def is None:
        message = f"step '{step}' is not defined in the workflow"
        _fail_instance(cur, inst, step, message)
        _finish_job(cur, job, "dead", message)
        return None

    kind = step_kind(step_def)
    if kind in ("branch", "delay"):
        _advance_to(cur, inst, step, 0.0, notify=False)
        _finish_job(cur, job, "done")
        return None

    attempt = job["attempts"] + 1
    cur.execute(
        "UPDATE workflow_instances SET status = 'running', current_step = %s, current_step_attempts = %s WHERE id = %s",
        (step, attempt, instance_id),
    )
    # An execution left 'running' by a worker that died is closed here.
    cur.execute(
        "UPDATE workflow_step_executions SET status = 'failed', completed_at = now(), "
        "error_details = 'worker lost (lease expired)' "
        "WHERE instance_id = %s AND step_name = %s AND status = 'running'",
        (instance_id, step),
    )

    if kind == "wait_for_event":
        _insert_execution(cur, inst, step, 1)
        timeout = step_def.get("timeout_seconds")
        if timeout:
            _enqueue(cur, instance_id, step, float(timeout), kind="wait_timeout")
        _finish_job(cur, job, "done")
        return None

    config, pre_error = dict(step_def.get("config", {})), None
    connection_id = step_def.get("connection_id")
    if connection_id:
        cur.execute("SELECT config FROM connections WHERE id = %s", (connection_id,))
        row = cur.fetchone()
        if row and row["config"]:
            merged = dict(row["config"])
            merged.update(config)          # the step's own values win over the connection's
            config = merged
        else:
            pre_error = f"connection '{connection_id}' not found"
    execution_id = _insert_execution(cur, inst, step, attempt)
    return StepWork(
        instance_id=instance_id, step=step, step_def=step_def, execution_id=execution_id, attempt=attempt,
        data=inst["data"] or {}, config=config, request_id=inst["request_id"], workflow_name=inst["workflow_name"],
        started=time.monotonic(), pre_error=pre_error,
    )


def finish_step(cur, job: dict, work: StepWork, outcome: StepOutcome, worker_id: str) -> None:
    """One transaction: check the lease, save the result, advance the instance, queue the next job."""
    inst = _lock_instance(cur, work.instance_id)
    cur.execute("SELECT status, locked_by FROM jobs WHERE id = %s FOR UPDATE", (job["id"],))
    current = cur.fetchone()
    if not current or current["status"] != "running" or current["locked_by"] != worker_id:
        log.warning("Lease lost; discarding the result", job_id=job["id"], instance_id=work.instance_id)
        return
    if inst is None or inst["status"] in TERMINAL or inst["current_step"] != work.step:
        cur.execute(
            "UPDATE workflow_step_executions SET status = 'failed', completed_at = now(), "
            "error_details = 'instance cancelled or moved on, result discarded' WHERE id = %s",
            (work.execution_id,),
        )
        _finish_job(cur, job, "done")
        return

    duration = time.monotonic() - work.started
    labels = {"workflow_name": work.workflow_name, "step_name": work.step}
    if outcome.ok:
        data_in = work.data
        returned = data_in if outcome.data is None else outcome.data
        delta = {k: v for k, v in returned.items() if k not in data_in or data_in[k] != v}
        removed = [k for k in data_in if k not in returned]
        data = dict(inst["data"] or {})
        data.update(delta)
        for key in removed:
            data.pop(key, None)
        cur.execute("UPDATE workflow_instances SET data = %s WHERE id = %s", (_dumps(data), work.instance_id))
        cur.execute(
            "UPDATE workflow_step_executions SET status = 'completed', completed_at = now(), output_data = %s WHERE id = %s",
            (_dumps(delta), work.execution_id),     # only what the step changed
        )
        step_execution_total.labels(status="completed", **labels).inc()
        step_duration_seconds.labels(action_type=work.action_id, **labels).observe(duration)
        inst["data"] = data
        _finish_job(cur, job, "done")
        _advance_to(cur, inst, work.step_def.get("next"), 0.0, notify=False)
        return

    max_attempts, delay = retry_policy(work.step_def)
    error = outcome.error or "Unknown error"
    cur.execute(
        "UPDATE workflow_step_executions SET status = 'failed', completed_at = now(), error_details = %s WHERE id = %s",
        (error, work.execution_id),
    )
    step_execution_total.labels(status="failed", **labels).inc()
    step_duration_seconds.labels(action_type=work.action_id, **labels).observe(duration)
    if work.attempt < max_attempts:
        step_retry_total.labels(**labels).inc()
        cur.execute(
            "UPDATE jobs SET status = 'queued', attempts = %s, claims = 0, locked_by = NULL, locked_until = NULL, "
            "run_at = now() + make_interval(secs => %s), last_error = %s WHERE id = %s",
            (work.attempt, delay, error, job["id"]),
        )
        cur.execute("SELECT pg_notify(%s, '')", (NOTIFY_CHANNEL,))
    else:
        _finish_job(cur, job, "dead", error)
        _fail_instance(cur, inst, work.step, error, record=False)


def release_job(cur, job: dict, worker_id: str, delay_seconds: float = 10.0) -> None:
    """Put a job back after an engine error (not a handler failure), to be tried again shortly."""
    cur.execute(
        "UPDATE jobs SET status = 'queued', locked_by = NULL, locked_until = NULL, "
        "run_at = now() + make_interval(secs => %s) WHERE id = %s AND locked_by = %s",
        (delay_seconds, job["id"], worker_id),
    )


def seconds_until_next_job(cur, cap: float) -> float:
    """How long until a queued job is due or a running job's lease expires, at most `cap`."""
    cur.execute(
        "SELECT EXTRACT(EPOCH FROM (LEAST((SELECT min(run_at) FROM jobs WHERE status = 'queued'), "
        "(SELECT min(locked_until) FROM jobs WHERE status = 'running')) - now())) AS seconds"
    )
    seconds = cur.fetchone()["seconds"]
    return cap if seconds is None else max(0.0, min(float(seconds), cap))


def queue_stats(cur) -> dict:
    """Queue depth and age, for the health check."""
    cur.execute(
        "SELECT count(*) FILTER (WHERE status = 'queued' AND run_at <= now()) AS due, "
        "       count(*) FILTER (WHERE status = 'running') AS running, "
        "       EXTRACT(EPOCH FROM now() - min(run_at) FILTER (WHERE status = 'queued' AND run_at <= now())) AS oldest_due_seconds "
        "FROM jobs WHERE status IN ('queued', 'running')"
    )
    stats = cur.fetchone()
    cur.execute("SELECT count(*) AS dead FROM jobs WHERE status = 'dead'")
    return {
        "due": stats["due"], "running": stats["running"], "dead": cur.fetchone()["dead"],
        "oldest_due_seconds": None if stats["oldest_due_seconds"] is None else round(float(stats["oldest_due_seconds"]), 1),
    }


# ------------------------------------------------------------------ state transitions

def _advance_to(cur, inst: dict, name: Optional[str], offset: float, notify: bool = True) -> None:
    """Move the instance to step `name`. Branch and delay steps are resolved here; the first action or
    wait step becomes a job, with run_at pushed out by any delays passed on the way.

    `notify` says whether to wake idle workers about the new job. A worker that has just finished a step
    passes False: it claims the next job itself, and a NOTIFY per step would make every committing
    transaction queue on PostgreSQL's global notify lock. A job due later always notifies, so a dispatcher
    that is sleeping learns it has an earlier deadline."""
    steps, data, instance_id = inst["definition"].get("steps", {}), inst["data"] or {}, str(inst["id"])
    for _ in range(MAX_INLINE_STEPS):
        if name in (None, "end"):
            if offset > 0:
                _enqueue_step(cur, instance_id, "end", offset, notify)
            else:
                _complete_instance(cur, inst)
            return
        step_def = steps.get(name)
        if step_def is None:
            _fail_instance(cur, inst, name, f"step '{name}' is not defined in the workflow")
            return
        kind = step_kind(step_def)
        if kind == "branch":
            result = evaluate_condition(data, step_def.get("condition", {}))
            target = step_def.get("on_true") if result else step_def.get("on_false")
            _record_control(cur, inst, name, {"branch_result": result, "next_step": target})
            name = target
        elif kind == "delay":
            seconds = int(step_def.get("duration_seconds", 60))
            _record_control(cur, inst, name, {"delay_seconds": seconds})
            offset += seconds
            name = step_def.get("next")
        else:
            _enqueue_step(cur, instance_id, name, offset, notify)
            return
    _fail_instance(cur, inst, name or "end",
                   f"more than {MAX_INLINE_STEPS} branch or delay steps in a row (cycle in the definition?)")


def _enqueue_step(cur, instance_id: str, step: str, offset: float, notify: bool) -> None:
    cur.execute(
        "UPDATE workflow_instances SET status = 'running', current_step = %s, current_step_attempts = 0 WHERE id = %s",
        (step, instance_id),
    )
    _enqueue(cur, instance_id, step, offset, notify=notify)


def _enqueue(cur, instance_id: str, step: str, offset: float = 0.0, kind: str = "run_step", notify: bool = True) -> None:
    cur.execute(
        "INSERT INTO jobs (instance_id, step_name, kind, run_at) VALUES (%s, %s, %s, now() + make_interval(secs => %s))",
        (instance_id, step, kind, offset),
    )
    if notify or offset > 0:
        cur.execute("SELECT pg_notify(%s, '')", (NOTIFY_CHANNEL,))    # delivered when this transaction commits


def _on_wait_timeout(cur, job: dict, inst: dict) -> None:
    instance_id, step = str(inst["id"]), job["step_name"]
    cur.execute(
        "SELECT id FROM workflow_step_executions WHERE instance_id = %s AND step_name = %s AND status = 'running'",
        (instance_id, step),
    )
    waiting = cur.fetchone()
    if inst["current_step"] == step and inst["status"] == "running" and waiting:
        message = f"wait step '{step}' timed out"
        cur.execute(
            "UPDATE workflow_step_executions SET status = 'failed', completed_at = now(), error_details = %s WHERE id = %s",
            (message, waiting["id"]),
        )
        _fail_instance(cur, inst, step, message, record=False)
    _finish_job(cur, job, "done")


def _lock_instance(cur, instance_id: str) -> Optional[dict]:
    cur.execute(
        "SELECT i.id, i.status, i.current_step, i.data, i.request_id, i.created_at, v.definition, w.name AS workflow_name "
        "FROM workflow_instances i "
        "JOIN workflow_versions v ON v.id = i.workflow_version_id "
        "JOIN workflows w ON w.id = v.workflow_id "
        "WHERE i.id = %s FOR UPDATE OF i",
        (instance_id,),
    )
    return cur.fetchone()


def _insert_execution(cur, inst: dict, step: str, attempt: int) -> str:
    cur.execute(
        "INSERT INTO workflow_step_executions (instance_id, step_name, status, attempts, started_at, request_id) "
        "VALUES (%s, %s, 'running', %s, now(), %s) RETURNING id",
        (str(inst["id"]), step, attempt, inst["request_id"]),
    )
    return str(cur.fetchone()["id"])


def _record_control(cur, inst: dict, step: str, output: dict) -> None:
    cur.execute(
        "INSERT INTO workflow_step_executions (instance_id, step_name, status, attempts, started_at, completed_at, "
        "output_data, request_id) VALUES (%s, %s, 'completed', 1, now(), now(), %s, %s)",
        (str(inst["id"]), step, _dumps(output), inst["request_id"]),
    )


def _complete_instance(cur, inst: dict) -> None:
    cur.execute("UPDATE workflow_instances SET status = 'completed', current_step = NULL WHERE id = %s", (str(inst["id"]),))
    _record_workflow_end(inst, "completed")


def _fail_instance(cur, inst: dict, step: str, message: str, record: bool = True) -> None:
    instance_id = str(inst["id"])
    cur.execute("UPDATE workflow_instances SET status = 'failed' WHERE id = %s", (instance_id,))
    if record:
        cur.execute(
            "INSERT INTO workflow_step_executions (instance_id, step_name, status, attempts, started_at, completed_at, "
            "error_details, request_id) VALUES (%s, %s, 'failed', 1, now(), now(), %s, %s)",
            (instance_id, step, message, inst["request_id"]),
        )
    log.error("Workflow failed", instance_id=instance_id, step=step, error=message)
    workflow_errors_total.labels(workflow_name=inst["workflow_name"], error_type="step_failure").inc()
    _record_workflow_end(inst, "failed")


def _record_workflow_end(inst: dict, status: str) -> None:
    created = inst.get("created_at")
    workflow_completed_total.labels(workflow_name=inst["workflow_name"], status=status).inc()
    if created is not None:
        from datetime import datetime, timezone
        seconds = (datetime.now(timezone.utc) - created).total_seconds()
        workflow_duration_seconds.labels(workflow_name=inst["workflow_name"], status=status).observe(seconds)


def _finish_job(cur, job: dict, status: str, error: Optional[str] = None) -> None:
    """A finished job is deleted, so the table only holds work to do and dead jobs to look at."""
    if status == "dead":
        cur.execute(
            "UPDATE jobs SET status = 'dead', finished_at = now(), last_error = COALESCE(%s, last_error) WHERE id = %s",
            (error, job["id"]),
        )
    else:
        cur.execute("DELETE FROM jobs WHERE id = %s", (job["id"],))
