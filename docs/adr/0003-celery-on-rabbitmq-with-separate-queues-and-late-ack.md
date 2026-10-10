# 0003. Celery on RabbitMQ with separate queues and late acknowledgement

- Status: Accepted - under review (known gaps: F-08, F-12, F-21, F-32)
- Date: 2026-10-07 (recorded retrospectively)

## Context

After the relay reads an outbox row (ADR 0002) something has to deliver it to a consumer, run it with bounded concurrency, and survive consumer crashes. Orchestration work (short, DB-bound, serialised per instance) and action work (long, I/O-bound, third-party calls) have very different profiles and should scale independently.

## Decision

Use Celery with RabbitMQ as broker (`src/shared/celery_app.py`).

Queues and roles (all processes run the same Docker image with a different command, see `docker-compose.yml`):

| Process | Command / entry point | Consumes |
|---|---|---|
| `api` | gunicorn, 4 uvicorn workers | none (produces via outbox) |
| `relay` | `src/relay/entrypoint/main.py` | none (outbox to broker) |
| `engine` | `celery ... -Q orchestration_queue` | `orchestration_queue` (task `engine.orchestrate`) |
| `worker` x2 | `celery ... -Q actions_queue` | `actions_queue` (task `worker.execute_action`) |

Reliability settings: `task_ack_late=True`, `worker_prefetch_multiplier=1`, `task_reject_on_worker_lost=True`, persistent delivery mode, soft/hard time limits of 300 s / 360 s.

Dead-letter topology: each work queue is declared with `x-dead-letter-exchange=''` and a routing key to `orchestration_dlq` / `actions_dlq`.

Retry policy in the engine task (`src/orchestration/entrypoint/celery_task.py`): lock contention retries every 5 s up to 12 times; unexpected errors retry every 10 s up to 3 times; a `NonRetryableError` is `Reject(requeue=False)` and goes to the DLQ.

## Alternatives considered

- Plain consumers on `pika` (the dependency is declared in `pyproject.toml` but is not imported anywhere): more control over acks and confirms, but reimplements retries, time limits and worker supervision.
- Other task frameworks (Dramatiq, RQ, Arq): simpler in places, weaker RabbitMQ and routing support or Redis-only.
- Kafka or SQS: different delivery model, no per-message delay without extra machinery.
- Temporal or a similar engine: replaces ADRs 0002, 0003 and 0005 together.

## Consequences

Positive:

- Crash safety from late ack plus `reject_on_worker_lost`: unacknowledged messages are redelivered.
- Orchestration and actions scale and fail independently; long actions cannot starve state transitions.
- Mature supervision, time limits and metrics hooks come with Celery.

Negative / known gaps:

- A Celery retry that is exhausted fails the task and the message is acknowledged (default `acks_on_failure_or_timeout`). It is not dead-lettered. Only the explicit `Reject(requeue=False)` path reaches a DLQ, so `docs/reliability.md` overstates the DLQ guarantee. Nothing consumes or alerts on the DLQs (F-08).
- The result backend was hard-coded to `redis://redis:6379/1`, ignoring `REDIS_URL`, and is unused because tasks return `None` (F-21). Removed on 2026-10-10 (`task_ignore_result=True`), which also lets Redis have a password.
- Concurrency is not configured; Celery defaults to the CPU count per process, which interacts with DB pool sizing (ADR 0012, F-14). `docs/scalability.md` assumes gevent for action workers; the compose file uses the default prefork pool.
- `beat_schedule` is defined but no `beat` process exists in compose (ADR 0007, F-07).
- RabbitMQ and Redis ports were published to the host with default credentials (F-12). Fixed on 2026-10-10: they are no longer published and require generated passwords (ADR 0020).
- Celery 5.5 does not start against RabbitMQ 4 out of the box: its remote-control (pidbox) queues are transient and non-exclusive, which RabbitMQ 4 rejects, so every worker crash-loops. Found on 2026-10-10. Compose now mounts `infrastructure/rabbitmq/celery-compat.conf` to permit the deprecated feature. This is a stopgap, because RabbitMQ will remove the feature in a future major version (F-32).

## References

- `src/shared/celery_app.py`, `src/shared/constants.py`
- `src/orchestration/entrypoint/celery_task.py`, `src/worker/task.py`
- `docker-compose.yml`, `docs/worker-and-scheduler.md`
- Related: ADR 0002, ADR 0006
