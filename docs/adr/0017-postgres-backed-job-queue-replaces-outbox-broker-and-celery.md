# 0017. A PostgreSQL job queue replaces the outbox, RabbitMQ, Celery and Redis

- Status: Accepted
- Date: 2026-10-10 (proposed and accepted the same day; implemented on branch `redesign-postgres-queue`)

## Context

The first design moved work through `engine tx -> outbox -> relay -> RabbitMQ -> worker -> outbox -> relay -> RabbitMQ -> engine tx`, with a Redis lock to serialise events per instance, Celery for consumption and retries, and a sweeper to rescue what slipped through. PostgreSQL was already the source of truth and, through the outbox, already the queue; RabbitMQ only carried rows from one table to a consumer that wrote straight back to the same database, and Redis only provided a lock.

That cost a lot for what it delivered: nine or ten containers, four database transactions and two broker hops per step, up to a second of relay polling per hop (a trivial workflow took about 6 s), and five cooperating reliability mechanisms, of which the recovery sweeper never ran and the dead-letter queues had no consumer. The audit's reliability, latency and operations findings mostly came from this plumbing. The throughput target in the old docs (1,000 jobs per second) had never been measured, and nothing in the product needs it.

## Decision

A `jobs` table in PostgreSQL is the only queue, consumed directly by workers. Details of how a job runs are in ADR 0018.

- A job is `(instance_id, step_name, kind, status, run_at, attempts, claims, locked_by, locked_until, last_error)`. Status is `queued`, `running` or `dead`; **finished jobs are deleted**, so the table holds only work to do and jobs that gave up, and no purge job is needed.
- Workers claim with `UPDATE jobs ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1)`. A job is claimable when it is `queued` and due, or `running` with an expired lease.
- `run_at` is the single mechanism for time: delays, retry back-off and `wait_for_event` timeouts.
- Crash recovery is lease expiry. A job claimed `JOB_MAX_CLAIMS` times without finishing is marked `dead` and its instance failed.
- Workers learn about new work through `LISTEN/NOTIFY`, plus a dispatcher that sleeps exactly until the next job is due. `NOTIFY` is sent only where someone else must be woken (see ADR 0018 for why not on every step).
- The stack is four containers: frontend, api, worker, postgres. `celery`, `kombu`, `redis`, `pika` and `boto3` are gone from the dependencies.

Upgrading an existing database is migration `002_job_queue.sql`, which creates `jobs`, turns unfinished instances into jobs so they resume, and drops the outbox.

## Alternatives considered

- Keep the design and fix it (a working sweeper, `LISTEN/NOTIFY` into the relay, the right index, metrics from every process). Least change, but keeps every moving part and the two-hop latency.
- Keep Celery and RabbitMQ but drop the Redis lock and merge engine and worker. Removes less; still needs the outbox and relay for atomic dispatch.
- A PostgreSQL queue library (Procrastinate, PgQueuer). Worth considering; the property needed is enqueueing the next job in the same transaction as the instance update, and the custom version is small.
- Temporal or a similar engine: stronger guarantees, but a large new dependency and programming model.
- Buy rather than build (n8n, Activepieces) if the goal is to run automations rather than to own an engine.

## Consequences

Positive:

- State change and next-job enqueue are one transaction by construction. No relay, no dual write, no relay latency: a three-step workflow now finishes in about 100 ms.
- Far fewer failure modes, and the queue is inspectable with SQL.
- 260 MiB for the whole stack, and one worker type to monitor. The worker serves its own Prometheus metrics, which closes the old gap where engine metrics were recorded where nothing exposed them.

Negative / risks:

- **Throughput is bounded by one PostgreSQL.** Measured on a pinned laptop core: about 215 to 245 fast steps per second on 1 CPU and about 400 to 430 on 2 (see `docs/scalability.md`). That is ample for the product, far below 1,000 per second, and scaling means a bigger database.
- **Benchmarking found three implementation problems, all fixed and tested:** a `NOTIFY` per step serialised every commit on PostgreSQL's global notify lock (about 80 steps/s cap); `psycopg2` closed returned connections beyond `minconn`, reconnecting on almost every use; and many threads exhausted the pool and then PostgreSQL's connection limit.
- `LISTEN` needs a direct or session-pooled connection (not PgBouncer in transaction mode).
- Postgres is a single point of failure for state and queue, as it already was for state. Back it up.
- Table churn: finished jobs are deleted, so autovacuum must keep up; so does the deletion of finished runs after `RETENTION_DAYS` (ADR 0022).
- No lease heartbeat: a step longer than `JOB_LEASE_SECONDS` is run again by another worker.
- Upgrading needs a stop, migrate, start; old messages in the outbox are discarded.

## References

- `src/engine/runtime.py`, `src/engine/worker.py`, `src/worker/main.py`
- `infrastructure/postgres/init.sql`, `infrastructure/postgres/migrations/002_job_queue.sql`
- `tests/integration/` (engine, worker, API flow, migration), `benchmarks/`, `docs/scalability.md`
- Related: ADR 0018
- Replaced decisions (their ADRs were deleted with the code): transactional outbox with a polling relay; Celery on RabbitMQ with late ack and dead-letter queues; per-instance Redis lock; step-level idempotency check in the worker; recovery sweeper.
