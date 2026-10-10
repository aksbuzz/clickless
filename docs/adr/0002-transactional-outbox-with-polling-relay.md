# 0002. Transactional outbox with a polling relay

- Status: Accepted - under review (known gaps: F-13)
- Date: 2026-10-07 (recorded retrospectively)

## Context

A workflow start, a step transition and an action result each change database state and must also cause a message to be delivered to RabbitMQ. Writing to PostgreSQL and publishing to the broker are two separate systems, so a crash between them either loses the message (job never runs) or publishes a message for state that was rolled back. For a workflow engine a lost job is worse than a duplicate one.

The system also needs delayed delivery: `delay` steps, step retries and `wait_for_event` timeouts.

## Decision

No component publishes to RabbitMQ directly. API, engine and worker INSERT a row into the `outbox` table in the same transaction as the state change they are making:

- API: `src/api/service.py` (`start_workflow`, `trigger_webhook`, `process_external_trigger`, `send_event`)
- Engine: `PostgresWorkflowRepository.schedule_message` in `src/orchestration/adapters/postgres_unit_of_work.py`
- Worker: result insert in `src/worker/service.py`

A separate `relay` process (`src/relay/entrypoint/main.py`) polls the table:

```sql
SELECT id, destination, payload, request_id FROM outbox
WHERE processed_at IS NULL AND publish_at <= NOW()
ORDER BY publish_at LIMIT <batch> FOR UPDATE SKIP LOCKED
```

For each row it calls `celery_app.send_task(...)` and, in the same transaction, sets `processed_at`. `FOR UPDATE SKIP LOCKED` allows several relay replicas. `publish_at` is the delay mechanism: a row in the future is ignored until due. Batch size is 100 and the idle sleep is a fixed 1.0 s (`POLL_INTERVAL_SECONDS`).

## Alternatives considered

Several of these are already analysed in `docs/worker-and-scheduler.md`.

- Publish directly after commit (dual write): simplest, but loses messages on a crash between commit and publish.
- RabbitMQ delayed-message plugin or TTL plus dead-letter routing: removes polling, but gives up the atomic state-change-plus-message guarantee.
- Redis sorted set scheduler: very low latency, but not transactional with PostgreSQL.
- `LISTEN/NOTIFY` as a wake-up signal with polling as fallback: lowers latency, described in the docs as the preferred improvement, not implemented.
- A dedicated workflow engine (Temporal, Conductor): removes the relay and most of the engine, at the cost of a large new dependency.

## Consequences

Positive:

- State and dispatch are atomic. A crash leaves either both or neither, and unrelayed rows are picked up on restart.
- One mechanism covers immediate dispatch, delays, retries and timeouts.
- Relays scale horizontally without coordination.

Negative / known gaps (see audit F-13):

- Every step costs two relay hops (engine to worker, worker to engine). With a 1 s idle sleep each hop can add up to about 1 s, which conflicts with the 2 s scheduling target in `docs/scalability.md`.
- `init.sql:66` indexes `(processed_at) WHERE processed_at IS NULL`, but the query orders and filters on `publish_at`. The docs describe an index on `publish_at`.
- There is no purge or archival of processed rows; the table grows without bound.
- A row whose `destination` has no task mapping is skipped but never marked processed, so it is re-selected on every poll and, with enough such rows, can occupy the head of the batch.
- `send_task` is used without publisher confirms; a broker failure after the call but before persistence loses a message that is already marked processed.
- The relay holds a transaction (and its row locks) open while publishing a whole batch.
- `docs/scalability.md` refers to `RELAY_BATCH_SIZE` and `RELAY_POLL_INTERVAL_MS`; neither exists.

## References

- `src/relay/service.py`, `src/relay/entrypoint/main.py`
- `infrastructure/postgres/init.sql` (`outbox`)
- `docs/reliability.md`, `docs/worker-and-scheduler.md`
- Related: ADR 0003, ADR 0006
