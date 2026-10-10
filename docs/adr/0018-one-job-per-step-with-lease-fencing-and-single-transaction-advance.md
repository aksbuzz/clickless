# 0018. One job per step, with lease fencing and a single-transaction advance

- Status: Accepted
- Date: 2026-10-10
- Depends on: ADR 0017

## Context

Workflows here are sequential: an instance has at most one step in flight. The old runtime spread a step over two queues and three event types, guarded duplicates with a Redis lock and status checks, held a database transaction across the whole handler call, and left several failure paths with the instance stuck in `running` forever. It needed an execution model with one mechanism for ordering, crashes and duplicates.

## Decision

Run each step as one job and advance the instance in the same transaction that records the step's result (`src/engine/runtime.py`).

For a claimed job (`StepRunner.run_one`):

1. **Claim** (`claim_job`): take the next due job and set the lease. A job already claimed `JOB_MAX_CLAIMS` times is marked `dead` and its instance failed.
2. **Begin** (`begin_step`, short transaction): lock the instance row (`FOR UPDATE`). If the instance is terminal, delete the job and stop. Close any attempt a dead worker left `running`. Insert a `running` execution row for this attempt. Load the step's connection credentials. A step that needs no handler (a branch, a delay, `end`, arming a `wait_for_event`) is finished here.
3. **Run** (`execute_step`, no transaction open): resolve `{{templates}}` once for every handler (keys a handler lists in `untemplated_keys` are left as written), call the handler on a copy of the data, and turn any failure, including an unknown action or an exception, into a failed outcome with a reason.
4. **Finish** (`finish_step`, one transaction): lock the instance, then lock the job and check the lease is still ours (`status = 'running' AND locked_by = me`); if not, discard the result. If the instance was cancelled or moved on, mark the attempt discarded and delete the job. On success store only the keys the step changed as `output_data`, apply the change and any removals to the instance data, delete the job, and advance. On failure, requeue the job after `retry.delay_seconds` while `retry.max_attempts` allows, otherwise mark the job `dead` and the instance `failed` with the error text.

Advancing (`_advance_to`) resolves control steps inside the transaction: `branch` evaluates its condition, `delay` adds its duration to the next job's `run_at`, `end` completes the instance. The first action or `wait_for_event` step becomes a job. More than 100 control steps in a row fails the instance (cycle guard).

`wait_for_event`: the job arms the wait (a `running` execution) and, with `timeout_seconds`, queues a `wait_timeout` job. `send_event` locks the instance, completes the wait, deletes the timeout job and advances. The timeout job fails the instance only if the wait is still open.

`cancel_instance` and `send_event` take the same instance lock as `begin_step` and `finish_step`, so they serialise with a step finishing without any external lock.

**Notifications.** A finishing worker claims the next job itself, so it sends no `NOTIFY`. Notifications are sent when someone else must be woken: an API start, an event, or a job queued for later (delay, retry, wait timeout). A `NOTIFY` on every enqueue made every committing transaction wait on PostgreSQL's global notify lock, which capped the whole system near 80 steps per second.

**Concurrency.** One worker process runs `WORKER_CONCURRENCY` runner threads sharing a small connection pool, plus a dispatcher thread holding one `LISTEN` connection and sleeping until the next job is due (`src/engine/worker.py`, `docs/worker-and-scheduler.md`).

Every non-success path ends in a terminal state or a scheduled retry: missing handler, undefined next step, missing connection, exhausted retries, a worker that keeps dying, a wait timeout, and an engine error (the job is released and retried after 10 s).

## Alternatives considered

- Keep orchestrator events (`START_WORKFLOW`, `STEP_COMPLETE`, `STEP_FAILED`) on the `jobs` table: fewer changes, but two job types per action and the guards that exist only to tolerate that design.
- Optimistic concurrency with a version column instead of a row lock.
- Hold one transaction across the handler: simplest, but ties up a connection and locks for the handler's duration.
- Resolve templates inside each handler (what the code did): easy to forget, and a second resolution would let a value containing `{{...}}` be resolved again.

## Consequences

Positive:

- No external lock and no stale-event guards: the row lock plus the lease fence cover cancel races, duplicate completions and stalled workers.
- No transaction is held during a handler, so connections are not tied to slow external calls and one pool serves many threads.
- A crashed or hung worker's job is retried by lease expiry, and its late result cannot corrupt state.
- Failures are always visible, with their reason, to the user (the step error text is stored and shown in the UI).
- Step executions are one row per attempt and store only what the step changed.

Negative / open points:

- **Side effects remain at-least-once.** Fencing protects database state, not the outside world: if a lease expires during a handler, another worker runs it again.
- **No lease heartbeat**, so the lease (`JOB_LEASE_SECONDS`, default 300 s) must exceed the slowest step. A hung handler holds a thread until its own timeout; threads cannot be killed.
- The cycle guard covers branch and delay steps only: saving such a loop is now refused ([ADR 0023](0023-validate-workflow-definitions-when-they-are-saved.md)), and the engine still stops one in an older stored version. A loop through action steps has no per-instance step cap yet.
- Only sequential workflows are supported: one live job per instance. Parallel branches would need per-branch state; the instance row lock would still serialise writes.
- Handlers must be stateless and thread-safe (they are called concurrently).

## References

- `src/engine/runtime.py`, `src/engine/steps.py`, `src/engine/worker.py`
- `tests/integration/test_engine.py`, `tests/integration/test_worker.py`, `tests/unit/test_engine_steps.py`, `tests/unit/test_execute_step.py`
- `docs/reliability.md`, `docs/worker-and-scheduler.md`
- ADR 0017
