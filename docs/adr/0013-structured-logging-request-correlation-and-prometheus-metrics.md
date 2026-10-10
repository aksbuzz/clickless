# 0013. Structured logging, request correlation, metrics and health

- Status: Accepted - under review (known gaps listed below)
- Date: 2026-10-07 (recorded after the fact; rewritten 2026-10-10 for the job-queue design)

## Context

A request fans out across the API and the worker, over seconds to hours. Operators need to follow one logical run end to end and see system health, without attaching a debugger to a worker.

## Decision

**Logging** (`src/shared/logging_config.py`): `structlog` rendering JSON to stdout, with context variables merged into every line.

**Correlation:** the API middleware generates a UUID `request_id` per HTTP request (`src/api/main.py`). It is stored on `workflow_instances` and copied onto every `workflow_step_executions` row. The worker binds `request_id`, `instance_id` and `step` into the logging context for every job it runs, reading the id from the instance row (`StepRunner.run_one`), so one id follows a run from the API call through every step, however many workers touch it.

**Metrics** (`src/shared/metrics.py`, `prometheus_client`):
- The API serves HTTP request count and latency at `GET /metrics` (API key required).
- The worker serves workflow and step metrics (`workflow_started_total`, `workflow_completed_total`, `workflow_duration_seconds`, `workflow_errors_total`, `step_execution_total`, `step_duration_seconds`, `step_retry_total`) on its own port, `WORKER_METRICS_PORT` (default 9100), inside the compose network.

**Health** (`src/api/health.py`): `GET /health` (API key required) reports two checks, PostgreSQL and the job queue. The queue check fails when the oldest *due* job has waited longer than `HEALTH_MAX_JOB_AGE_SECONDS` (default 30), which means no worker is taking jobs, and reports the counts of due, running and dead jobs. It returns 503 when degraded. `GET /ready` (public) checks only PostgreSQL and is the container readiness probe. The worker container's health check requests its metrics endpoint.

## Alternatives considered

- OpenTelemetry for traces, metrics and log correlation (W3C `traceparent` instead of a home-grown id).
- A hosted error tracker (Sentry) for exceptions.
- Prometheus multiprocess mode for the API's gunicorn workers.

## Consequences

Positive:

- JSON logs with consistent keys; one id links API logs to instance and step rows and to every worker log line for that run (the correlation no longer breaks after the first step).
- Workflow and step metrics are actually exposed, from the process that records them.
- `/health` notices a missing worker, which the previous health check could not.

Negative / known gaps:

- The API runs four gunicorn workers without Prometheus multiprocess mode, so each scrape of `/metrics` returns whichever worker answered.
- The HTTP `endpoint` label is the raw URL path, which includes instance and workflow UUIDs: unbounded label cardinality. `workflow_name` and `step_name` labels are user-defined and can grow without limit.
- The id is not returned to the caller (no `X-Request-ID` response header) and an inbound id is not honoured. Unhandled exceptions skip the context cleanup in the middleware.
- An idle system with no worker looks healthy until a job is queued; there is no worker heartbeat.
- No distributed tracing.

## References

- `src/shared/logging_config.py`, `src/shared/metrics.py`, `src/api/main.py`
- `src/api/health.py`, `src/api/routers/health.py`, `src/worker/main.py`, `src/engine/worker.py`
- `tests/unit/test_health.py`, `tests/integration/test_api_flow.py`
- Related: ADR 0018, ADR 0020
