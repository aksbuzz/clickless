# 0015. Module layout and a single image for all backend roles

- Status: Accepted - under review (known gaps: F-21, F-23)
- Date: 2026-10-07 (recorded retrospectively)

## Context

The backend is one codebase with several runtime roles (API, relay, engine, action worker, beat) that share models, connectors, the database layer and the Celery app. The project is small and developed by few people, and recent commits (`e020aeb`, `2b0daac`) deliberately flattened over-layered code.

## Decision

One Python package tree under `src/`, one Docker image, different commands per role in `docker-compose.yml`:

| Package | Role | Shape |
|---|---|---|
| `src/api` | HTTP API, webhook ingestion | routers, then `service.py`, then `repository.py`; `errors.py` plus exception handlers; `trigger_handlers/` |
| `src/orchestration` | engine | ports and adapters: `domain/`, `application/`, `adapters/` (unit of work, Redis lock), `entrypoint/` (Celery tasks) |
| `src/worker` | action execution | `task.py`, then `service.py`, then `handlers/` and a registry |
| `src/relay` | outbox relay | `service.py` plus an entry point loop |
| `src/shared` | cross-cutting | db, Celery app, connector catalogue, trigger port, metrics, logging, constants |

Imports use `src.*` with `PYTHONPATH=/app`. The Dockerfile is a two-stage build (Poetry in the builder, runtime copies `/usr/local` and `src/`) and runs as a non-root user. Dev overrides (`docker-compose.override.yml`) mount `./src` and use `--reload`.

## Alternatives considered

- Separately built images per role: smaller attack surface and independent deploys, more build and release overhead.
- Hexagonal layering everywhere: consistent, but ceremony for CRUD-style API code.
- Separate repositories or services per role.

## Consequences

Positive:

- One build, one dependency set, easy local development, shared code without publishing packages.
- The engine, which has the most invariants, keeps the strictest layering.

Negative / known gaps:

- Dependencies are not role-specific: the relay and workers carry FastAPI and gunicorn, and the API carries Celery and the worker's HTTP clients. Unused packages are declared (`pika`, `boto3`), and `ruff` and `black`, which the Makefile calls, are not.
- Layering leaks: the engine's Celery module imports `src.api.service` to run recovery (ADR 0007), `src/api/health.py` imports the Celery app, and `src/orchestration/domain/models.py` re-exports `EventType` from `shared` "for backward compat". There are unused modules (`src/orchestration/adapters/postgres_lock.py`, the `initial_step` and `final_step` handlers, the `active_workflows` gauge).
- Compose runs the `api`, `engine`, `worker` and `relay` containers without `depends_on` on Postgres for three of them, without healthchecks, restart policies or resource limits. The Dockerfile default `CMD` (`python -m src.api.main`) does nothing because `main.py` has no `__main__` block; every service relies on its compose `command`.
- `docker-compose.override.yml` is picked up automatically, so a plain `docker compose up` runs dev mode: `uvicorn --reload`, source mounts, debug logs and an `adminer` service on port 8080.
- The README layout section still lists a nonexistent `engine/` directory (F-22).

## References

- `Dockerfile`, `docker-compose.yml`, `docker-compose.override.yml`, `pyproject.toml`
- `src/` tree
- Related: ADR 0003, ADR 0005, ADR 0007
