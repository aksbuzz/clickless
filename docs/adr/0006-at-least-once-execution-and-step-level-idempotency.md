# 0006. At-least-once execution with step-level idempotency

- Status: Accepted - under review (known gaps: F-16)
- Date: 2026-10-07 (recorded retrospectively)

## Context

Exactly-once execution is not achievable across PostgreSQL, a broker and third-party APIs. The system has to choose between at-most-once (jobs can be lost) and at-least-once (jobs can repeat). For automation, silently losing a job is the worse failure.

## Decision

Guarantee at-least-once delivery end to end, and make repeats harmless where the platform can:

- Producer side: transactional outbox (ADR 0002).
- Consumer side: late acknowledgement with redelivery on worker loss (ADR 0003).
- Orchestrator: duplicate and stale events are ignored by state guards (ADR 0005).
- Action worker: before running a handler, `WorkerService.execute_action` looks up the latest `workflow_step_executions` row for `(instance_id, step_name)` and returns without doing anything if its status is `completed`.
- Handler failures (exceptions or `FAILURE` results) are converted to a `STEP_FAILED` event through the outbox; the engine owns retry policy.

Making external side effects idempotent is explicitly left to connector authors (`docs/reliability.md`).

## Alternatives considered

- At-most-once (early ack, no outbox): simpler, loses work on any crash.
- Worker claims the step atomically (`UPDATE ... SET status='running' WHERE status='pending' RETURNING`) before calling the handler, so only one worker can execute an attempt.
- Persist the handler result keyed by `(instance, step, attempt)` and replay it on repeats.
- Pass idempotency keys to providers that support them (GitHub, Slack and Trello webhooks and APIs generally do not offer them for these calls).

## Consequences

Positive:

- No lost jobs from API, relay, broker or worker crashes.
- Orchestration repeats are safe.

Negative / known gaps (F-16):

- The worker's dedupe check reads a status that only the engine sets, when it processes `STEP_COMPLETE`. Between a handler succeeding and the engine processing its result, a redelivered action message runs the handler a second time. The docs describe the check as preventing double execution; it only narrows the window.
- The step execution row is created `pending` by the engine and the worker never moves it to `running`, so there is no claim to detect a concurrent duplicate.
- The handler runs while a database connection and transaction are held open (`with db_cursor()` wraps the whole call, up to the 300 s limit).
- Built-in handlers (Slack, GitHub, Trello, HTTP, SQL execute) are not idempotent and send no idempotency keys, so repeats cause duplicate messages, issues, cards or writes.
- The sweeper (ADR 0007) can inject additional duplicates.

## References

- `src/worker/service.py`, `src/worker/task.py`
- `src/orchestration/application/orchestration_service.py` (guards)
- `docs/reliability.md`
- Related: ADR 0002, ADR 0003, ADR 0005, ADR 0007
