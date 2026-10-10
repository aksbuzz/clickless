# 0005. Event-driven orchestrator serialised per instance with a Redis lock

- Status: Accepted - under review (known gaps: F-08, F-10, F-17)
- Date: 2026-10-07 (recorded retrospectively)

## Context

Several events can arrive for the same workflow instance at nearly the same time (a step result, a user event, a timeout, a recovery re-enqueue). State transitions must apply one at a time per instance, while different instances should run fully in parallel.

## Decision

The engine is a state machine driven by three events delivered through `orchestration_queue`: `START_WORKFLOW`, `STEP_COMPLETE`, `STEP_FAILED`.

`OrchestrationService.process_event` (`src/orchestration/application/orchestration_service.py`):

1. Takes a non-blocking Redis lock `lock:instance:{id}` with a 30 s TTL (`RedisLockService`). If it cannot, it raises `RetryableError` and the Celery task retries.
2. Inside the lock, runs one database transaction through the unit of work: load instance and version, mutate state, write step executions and outbox rows, commit.
3. Applies guards before acting: events for terminal instances are ignored; `START_WORKFLOW` is ignored unless the instance is `pending`; `STEP_COMPLETE` / `STEP_FAILED` are ignored unless `event.step_name == instance.current_step` (stale-event guard).

Transition behaviour: `end` completes the instance; `branch` is evaluated inline and recurses into the chosen target; `delay` writes an outbox row with a future `publish_at`; `wait_for_event` marks the step running and optionally schedules a timeout `STEP_FAILED`; any other step enqueues an action to `actions_queue`. `POST /instances/{id}/events` resumes a waiting step. Failure handling re-enqueues the action while `current_step_attempts < max_attempts`, else marks the instance `failed`.

## Alternatives considered

- `SELECT ... FOR UPDATE` on the instance row: makes PostgreSQL the single source of truth and removes Redis from the correctness path. A Postgres advisory-lock implementation exists in `src/orchestration/adapters/postgres_lock.py` but is not used anywhere.
- Consistent-hash routing so one consumer owns each instance: no lock, but more broker topology.
- Optimistic concurrency with a version column on `workflow_instances`: no lock, retries on conflict.
- Actor or durable-execution frameworks (Temporal).

## Consequences

Positive:

- Different instances proceed in parallel; ordering within an instance is preserved.
- Guards make the orchestrator tolerant of duplicate and out-of-order events (ADR 0006).

Negative / known gaps:

- Redis is on the correctness path, is not durable, and the lock is not a fencing lock. After a Redis restart or a TTL expiry two events for one instance can run concurrently. `find_instance` takes no row lock, so the database does not backstop this.
- The lock TTL (30 s) is far below the task time limit (300 s) and is never renewed.
- Writers outside the engine bypass the lock. `cancel_instance` updates `status` directly, and the engine's `save_instance` writes the full row back, so a cancel committed between the engine's read and write can be overwritten (F-17).
- The stale guard compares step names only; in a workflow that revisits the same step, a duplicate completion for an earlier visit is accepted.
- No cycle or depth guard on branch recursion (F-10).
- When retries are exhausted (Redis down, or repeated unexpected errors) the event is dropped and the instance stays `running` until something recovers it (ADR 0007, F-08).
- `_complete_current_step` re-reads the instance and definition to record metrics (an extra query per step).

## References

- `src/orchestration/` (domain, application, adapters, entrypoint)
- `src/api/routers/instances.py` (`/events`, `/cancel`)
- `docs/architecture.md`
- Related: ADR 0002, ADR 0006, ADR 0007
