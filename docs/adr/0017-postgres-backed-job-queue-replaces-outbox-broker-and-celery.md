# 0017. Postgres-backed job queue replaces the outbox, relay, RabbitMQ, Celery and the Redis lock

- Status: Proposed
- Date: 2026-10-10
- If accepted, supersedes ADR 0002, 0003, 0006 and 0007, and the locking part of ADR 0005. Those stay `Accepted` until then.

## Context

The audit (`docs/audit-2026-10-07.md`) found that the current runtime is a distributed-systems design that does not deliver what it promises, and that most of its open findings sit in the plumbing rather than the product:

- A single action step crosses `engine tx -> outbox -> relay -> RabbitMQ -> worker -> outbox -> relay -> RabbitMQ -> engine tx`: roughly 4 database transactions and 2 broker hops, plus up to 1 s of idle relay polling per hop (F-13).
- It needs 9 or 10 containers: nginx, api, engine, worker (x2), relay, beat (not deployed), Postgres, RabbitMQ, Redis.
- PostgreSQL is already the source of truth and, through the outbox, already the queue. RabbitMQ only carries rows from one Postgres table to a consumer that immediately writes back to Postgres. Redis only provides a per-instance lock and an unused result backend.
- Reliability needs five cooperating mechanisms (outbox, late ack, step idempotency, state guards, a sweeper), and the last two do not work as documented (F-07, F-08, F-16).

The stated target of 1,000 jobs/s and 2 s scheduling latency (`docs/scalability.md`) was never measured against this design.

## Decision

Make a `jobs` table in PostgreSQL the only queue, consumed directly by workers. See `spikes/pg-queue/` for a working implementation.

- A job is `(instance_id, step_name, kind, status, run_at, attempts, claims, locked_by, locked_until, last_error)`. Statuses: `queued`, `running`, `done`, `dead`, `cancelled`.
- Workers claim with `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1)`. A job is claimable when it is `queued` and due, or `running` with an expired lease (`locked_until < now()`). Claiming sets the lease.
- One mechanism for time: `run_at` carries delays, retry backoff and `wait_for_event` timeouts. This replaces `outbox.publish_at`.
- Crash recovery is lease expiry, replacing late ack, `reject_on_worker_lost` and the sweeper. A job claimed `MAX_CLAIMS` times without finishing is marked `dead` and its instance failed, replacing the DLQ for that case.
- Latency: workers `LISTEN` on a channel, enqueue does `pg_notify` in the same transaction (delivered on commit), and an idle worker sleeps until the earliest `run_at` or lease expiry (capped), not a fixed 1 s.
- Processes: `api` and one `worker` type that scales by replica count. Compose shrinks to frontend, api, worker and Postgres. The `engine`, `relay`, `beat`, RabbitMQ and Redis services, and the `celery`, `pika`, `redis` and `boto3` dependencies, go away.

## Alternatives considered

- Keep the current design and fix it (audit phases 2 and 3: `LISTEN/NOTIFY` into the relay, correct index, purge, working sweeper, metrics from every process). Least change, but keeps all the moving parts and the two-hop latency.
- Keep Celery and RabbitMQ but drop the Redis lock (use a row lock) and merge engine and worker. Removes less; still needs the outbox and relay for atomic dispatch.
- Adopt a Postgres queue library (Procrastinate, PgQueuer). Worth evaluating. The property to check is that the next job can be enqueued in the same transaction as the instance update, and that a lease/fencing check fits. The spike shows the custom version is about 430 lines including state transitions.
- Temporal or similar: strongest guarantees, but a large new dependency and a different programming model.
- Buy instead of build (n8n, Activepieces) if the goal is to run automations rather than to own an engine.

## Consequences

Positive:

- State change and next-job enqueue are one transaction by construction; there is no relay, so no dual write and no relay latency.
- Fewer failure modes: no broker redelivery semantics, no DLQ without a consumer, no lock outside the database.
- Visible and queryable: the queue is a table (`SELECT ... FROM jobs WHERE status = 'dead'`).
- Smaller operational surface: 4 containers instead of 9 or 10, and one worker type to monitor.

Negative / risks:

- **Throughput ceiling, unproven at the stated target.** With PostgreSQL and the workers sharing a pinned CPU (spike README, "Benchmarks"), the unoptimised spike reached about 150 steps/s on 1 CPU and 220 on 2 CPUs (200 and 290 with `synchronous_commit=off`) for fast internal steps, on a laptop core that is probably faster than a cloud vCPU. PostgreSQL used about 70% of the CPU per step (roughly 3.5 to 5 ms against 1.4 to 2 ms for the Python worker), and HTTP ingestion cost about 2.3 ms of CPU per accepted workflow. That is far below 1,000 jobs/s. Measured waste to remove first: commits per step grow from 3.7 to 13.7 as workers are added (idle polling and a `NOTIFY` that wakes every worker), and throughput drops at 16 workers. Likely improvements, none yet measured: merge the claim and begin transactions, drop redundant instance updates, claim in batches, wake one worker instead of all, and use `synchronous_commit=off` for worker connections only (never for the ingestion path, where an acknowledged webhook must be durable). First decide whether 1,000 jobs/s is a real requirement: it is about 86 million jobs a day.
- **Table churn.** Done jobs must be purged or deleted on completion, and autovacuum tuned; otherwise the claim query slows over time (the same issue the outbox has today, F-13).
- **Long handlers need a lease at least as long as the handler**, or a lease heartbeat. The spike has no heartbeat; the default lease equals the current 300 s limit.
- **`LISTEN/NOTIFY` needs session-level connections.** Listener connections must bypass PgBouncer in transaction mode. Polling at a short interval remains the fallback.
- Postgres is a single point of failure for both state and queue, as it already is for state.
- Loses the RabbitMQ management UI; queue depth and oldest-job age should become SQL-backed metrics.
- Migration needs a cutover plan: stop intake, drain or finish in-flight instances on the old path, then switch. In-flight `workflow_instances` are compatible because the instance and step-execution tables are unchanged apart from the semantics described in ADR 0018.

## Evidence

`spikes/pg-queue/` runs the seed workflow with the real handlers against a real PostgreSQL 17, and 20 tests pass, including crash recovery by lease expiry, a stale worker's result being discarded, poison jobs, delay without polling, and 300 instances over 4 workers with every step executed exactly once. See its README for the measurements and what the spike does not cover.

## References

- `spikes/pg-queue/` (schema, engine, tests, benchmarks, README). Its README also records the optimisation backlog and PostgreSQL tuning starting points, which were deliberately not implemented
- `docs/audit-2026-10-07.md` (F-07, F-08, F-13, F-14, F-15, F-16, F-17)
- ADR 0002, 0003, 0005, 0006, 0007
- Related: ADR 0018
