# 0018. One job per step, with lease fencing and a single-transaction advance

- Status: Proposed
- Date: 2026-10-10
- If accepted, supersedes the event model and the Redis lock in ADR 0005, and the step-idempotency part of ADR 0006. Depends on ADR 0017.

## Context

Today a step is spread over two queues and three event types. The engine receives `STEP_COMPLETE`, the worker receives the action, the worker writes a result event, and the engine guards against duplicates and stale events with a Redis lock plus checks on status and step name (ADR 0005). The worker holds a database transaction open for the whole handler call, and its duplicate check reads a status that only the engine sets later (ADR 0006, F-16). Cancel writes without the lock (F-17). Several failure paths leave the instance `running` forever (F-08).

Workflows in this product are sequential: there is no fan-out, so an instance has at most one step in flight.

## Decision

Run each step as one job, and advance the instance in the same transaction that records the step's result. Implemented in `spikes/pg-queue/pg_engine.py`.

For a claimed job:

1. **Begin (short transaction).** Lock the instance row (`FOR UPDATE`). If the instance is terminal, finish the job and stop. Mark any execution left `running` by a dead worker as failed. Insert a `running` step execution for this attempt. Load the connection config. Commit.
2. **Run the handler with no transaction open.** Templates are resolved once, centrally, before the handler runs, for every connector (fixes F-09 without touching each handler).
3. **Finish (one transaction).** Lock the instance, then lock the job and check the lease is still ours (`status = 'running' AND locked_by = me`). If not, discard the result. If the instance was cancelled or moved on, mark the execution discarded and finish the job. Otherwise:
   - success: store only the keys the step changed as the execution's `output_data`, apply changes and removals to the instance data, finish the job, and advance;
   - failure: if attempts remain under the step's retry policy, requeue the job with `run_at = now + delay_seconds` and reset its claim count; otherwise mark the job `dead` and the instance `failed` with the error.

Advancing (`_advance_to`) resolves control steps inline, in the same transaction: `branch` evaluates and continues, `delay` adds its duration to the next job's `run_at`, `end` completes the instance (or enqueues `end` at the delayed time). The first action or `wait_for_event` step becomes a job. More than 100 inline hops fails the instance, which catches branch/delay cycles.

`wait_for_event`: the job arms the wait (a `running` execution) and enqueues a `wait_timeout` job at `run_at = now + timeout_seconds`. `send_event` locks the instance, completes the wait, cancels the timeout job and advances. The timeout job fails the instance only if the wait is still open.

`cancel_instance` and `send_event` take the same instance row lock as the worker, so they serialise with step completion without any external lock.

Every non-success path ends in a terminal state or a scheduled retry: a missing handler, an undefined next step, a missing connection, exhausted retries, a worker that keeps dying, and a wait timeout all produce a `failed` instance with an error recorded on a step execution.

## Alternatives considered

- Keep orchestrator events (`START_WORKFLOW`, `STEP_COMPLETE`, `STEP_FAILED`) but move them onto the `jobs` table. Fewer changes, but keeps two job types per action step and the guards that exist only to tolerate that design.
- Optimistic concurrency with a version column on the instance instead of a row lock.
- Keep the Redis lock for the engine.
- Hold one transaction across the handler (simplest to reason about, but ties up a connection and locks for up to the handler timeout).

## Consequences

Positive:

- No external lock and no stale-event guards: the row lock plus the lease fence cover cancel races (F-17), duplicate completions and zombie workers.
- No transaction is held during a handler call, so pool pressure no longer depends on handler duration (F-14, F-16).
- A crashed or hung worker's job is retried by lease expiry; its late result cannot corrupt state.
- Unknown actions, dangling `next`, missing connections and similar errors fail the instance with a visible reason instead of stranding it (F-08, partly F-10).
- Step executions become one row per attempt, and `output_data` holds a delta instead of the whole instance data, ending quadratic growth (F-19, partly).

Negative / open points:

- **Side effects remain at-least-once.** Fencing protects database state, not the outside world: if a lease expires while a handler is still running, another worker runs the handler again. In the test for this, the handler ran twice and the following step ran once. Provider idempotency keys are still needed for non-idempotent actions.
- No lease heartbeat in the spike, so the lease must exceed the longest handler. A hung handler occupies its worker thread until the process restarts, as it does with Celery today.
- Inline limits only cover branch and delay cycles. A loop through action steps has no budget yet; a per-instance step cap is still needed, with definition validation (F-10).
- Only sequential workflows are supported by the one-live-job invariant. Adding parallel branches later needs per-branch state, though the instance row lock still serialises writes.
- Not covered by the spike: the HTTP layer, request-id propagation, metrics, purge of finished jobs, authentication, and the frontend. Step rows are now per attempt and `input_data` is empty; the UI has not been checked for this. The Python, SQL and HTTP handler security issues (F-02, F-05, F-06) are unchanged by this ADR.

## Evidence

`spikes/pg-queue/test_spike.py` (20 tests, all passing against PostgreSQL 17): seed workflow with real handlers; delta-only step output; central template resolution; unknown action, dangling `next`, missing connection and branch cycle all fail the instance; retry then success and retry exhaustion; delay as a future `run_at`; wait/event and wait timeout; crash recovery by lease expiry; stale worker result discarded with the handler running twice and state advancing once; poison job marked dead; cancel during a running step discards its result; 300 instances over 4 workers with each step completed exactly once.

## References

- `spikes/pg-queue/pg_engine.py`, `spikes/pg-queue/test_spike.py`
- `docs/audit-2026-10-07.md` (F-08, F-09, F-10, F-14, F-16, F-17, F-19)
- ADR 0005, ADR 0006, ADR 0017
