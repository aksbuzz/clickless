# 0007. Stuck-instance recovery sweeper

- Status: Accepted - under review (not operational: F-07)
- Date: 2026-10-07 (recorded retrospectively)

## Context

Even with the outbox and late acks, an instance can stop making progress: the engine exhausts its retries (ADR 0003), Redis is unavailable for longer than the retry window (ADR 0005), or a message is dropped. The instance then sits in `pending` or `running` forever with nothing scheduled to move it.

## Decision

Add a periodic sweeper (commit `03c71a2`):

- Celery task `engine.recover_stuck` (`src/orchestration/entrypoint/celery_task.py`) is registered in `beat_schedule` to run every 30 s.
- It calls `WorkflowManagementService.recover_stuck_instances(stale_seconds=60)` (`src/api/service.py`). An instance is stale when `workflow_instances.updated_at` is older than the threshold and its status is `pending` or `running`.
- Per instance: `pending` re-enqueues `START_WORKFLOW`; `running` with a completed latest step execution re-enqueues `STEP_COMPLETE`; otherwise it re-dispatches the current step's action to `actions_queue`.
- The same logic is exposed as `POST /admin/recover?stale_seconds=N`.

The docs present this as the safety net behind "Guarantee 5" in `docs/reliability.md`.

## Alternatives considered

- Per-step deadlines expressed as scheduled outbox events. The engine already does this for `wait_for_event` timeouts; the same mechanism could bound every dispatched action.
- Worker heartbeats with a lease per running step.
- Rely on broker redelivery only, and add alerting for instances idle beyond a threshold.

## Consequences

Not operational today:

- `docker-compose.yml` has no `beat` service (only `engine`, `worker`, `relay`), so the schedule never fires. The only trigger is the unauthenticated admin endpoint.

Unsafe when it does run (F-07):

- A `delay` step's execution is marked `completed` immediately, so a delay longer than 60 s looks stuck and is completed early by the sweeper.
- A `wait_for_event` step has no action: the sweeper re-dispatches it as an action named after the step, which has no handler.
- Any action running longer than 60 s is dispatched a second time, duplicating side effects (ADR 0006).
- The sweeper does not touch `updated_at`, so with a 30 s period and a 60 s threshold it re-enqueues the same instance every 30 s until state changes.
- `stale_seconds` is caller-controlled: `stale_seconds=0` re-dispatches every active instance.
- Recovery messages carry no `request_id`.
- The engine task imports `src.api.service` to reach this logic, a layering inversion (ADR 0015).

## References

- `src/shared/celery_app.py` (`beat_schedule`), `src/orchestration/entrypoint/celery_task.py`
- `src/api/service.py` (`recover_stuck_instances`), `src/api/repository.py` (`find_stuck_instances`), `src/api/routers/admin.py`
- `docs/reliability.md`
- Related: ADR 0005, ADR 0006
