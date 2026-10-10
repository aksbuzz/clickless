# 0013. Structured logging, request correlation and Prometheus metrics

- Status: Accepted - under review (known gaps: F-15)
- Date: 2026-10-07 (recorded retrospectively)

## Context

A request fans out across five processes and two queues, with delays of seconds to hours. Operators need to follow one logical run end to end and see system health, without attaching a debugger to a worker (commit `2f81df5`: "added metrics, health check, tracing").

## Decision

Logging (`src/shared/logging_config.py`): `structlog` rendering JSON to stdout, with context variables merged into every line. Celery signal handlers (`src/shared/celery_app.py`) bind `celery_task_id`, `celery_task_name`, `instance_id` and `request_id` per task and clear them afterwards.

Correlation: the API middleware generates a UUID `request_id` per HTTP request (`src/api/main.py`). It is stored on `workflow_instances`, `workflow_step_executions` and `outbox` (migration `001`), copied into the relay's Celery message headers, and re-bound in the worker or engine by `task_prerun`. The engine passes it forward when it writes new outbox rows.

Metrics (`src/shared/metrics.py`, `prometheus_client`): HTTP request count and latency (API middleware); workflow started/completed/duration, step executions/duration/retries and error counters (engine). Exposed at `GET /metrics` on the API.

Health: `GET /health` runs deep checks (Postgres, Redis, RabbitMQ, and a Celery `inspect().stats()` broadcast with a 2 s timeout) and returns 503 when degraded; `GET /ready` checks only Postgres.

## Alternatives considered

- OpenTelemetry for traces, metrics and log correlation (W3C `traceparent` instead of a home-grown id).
- A hosted error tracker (Sentry) for exceptions.
- StatsD or push-based metrics from short-lived workers.
- Per-process metrics HTTP servers, or the Prometheus multiprocess mode for gunicorn.

## Consequences

Positive:

- JSON logs with consistent keys; a single id links API logs to instance and step rows in the database.
- Useful metric names and sensible histogram buckets.

Negative / known gaps (F-15):

- The business metrics are incremented in the engine process, but only the API serves `/metrics`, and the registry is per process. Engine, worker and relay expose nothing, so `workflow_*` and `step_*` series are always empty at the API. The gauges `active_workflows` and `celery_queue_depth` are defined but never set.
- The API runs four gunicorn workers without Prometheus multiprocess mode, so each scrape returns whichever worker answered.
- The HTTP `endpoint` label is the raw URL path, which includes instance and workflow UUIDs: unbounded label cardinality. `workflow_name` and `step_name` labels are user-defined and can grow without limit as well.
- Correlation breaks after the first action: the worker writes its result to the outbox without a `request_id` (`src/worker/service.py`), as does the recovery sweeper, so later steps log and store no id.
- The id is not returned to the caller (no `X-Request-ID` response header) and an inbound id is not honoured, which limits cross-system correlation. Unhandled exceptions skip the context cleanup in the middleware.
- `/health` fans out a Celery inspect call on every request, which is slow and unsuitable as a container liveness probe; no compose service defines a healthcheck for the application containers. `/health` and `/metrics` disclose worker names and Redis memory; since 2026-10-10 they require the API key (ADR 0020), while `/ready` stays public for probes.
- No distributed tracing, and `step_duration_seconds` records `action_type="unknown"`.

## References

- `src/shared/logging_config.py`, `src/shared/metrics.py`, `src/shared/celery_app.py`
- `src/api/main.py`, `src/api/health.py`, `src/api/routers/health.py`
- `infrastructure/postgres/migrations/001_add_request_id_tracing.sql`
- Related: ADR 0014
