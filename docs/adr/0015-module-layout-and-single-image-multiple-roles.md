# 0015. Module layout, and one image for the API and the worker

- Status: Accepted - under review (known gaps listed below)
- Date: 2026-10-07 (recorded after the fact; rewritten 2026-10-10 for the job-queue design)

## Context

The backend is one codebase with two runtime roles, the API and the worker, that share the database layer, the connector catalogue and the engine. The project is small and developed by few people.

## Decision

One Python package tree under `src/`, one Docker image, a different command per role in `docker-compose.yml`:

| Package | Role | Contents |
|---|---|---|
| `src/api` | HTTP API, webhook ingestion | routers, `service.py`, `repository.py`, `auth.py`, `health.py`, `errors.py` and exception handlers, `trigger_handlers/` |
| `src/engine` | the runtime | `runtime.py` (job queue and state machine, cursor-based), `steps.py` (pure logic), `worker.py` (runner, wake signal, threads) |
| `src/worker` | worker process and connector handlers | `main.py` (entry point), `registry.py`, `models.py`, `handlers/` |
| `src/shared` | cross-cutting | `db.py`, `errors.py`, `net_guard.py`, `logging_config.py`, `metrics.py`, connector catalogue, trigger port |

Dependencies point one way: `api` and `worker` import `engine` and `shared`; `engine` imports `shared` and the handler contract in `worker/models.py`; `shared` imports nothing from the others. Domain errors live in `src/shared/errors.py` so the engine can raise them without importing the API.

Imports use `src.*` with `PYTHONPATH=/app`. The Dockerfile is a two-stage build (Poetry in the builder, the runtime copies `/usr/local` and `src/`) and runs as a non-root user. Compose runs four services: `postgres`, `api` (gunicorn), `worker` (`python -m src.worker.main`) and `frontend`. `docker-compose.override.yml` is loaded automatically and adds dev conveniences (`uvicorn --reload`, source mounts, debug logs, an `adminer` service behind the `dev-tools` profile).

## Alternatives considered

- Separately built images per role: smaller attack surface and independent deploys, more build and release overhead.
- Hexagonal layering everywhere: consistent, but ceremony for CRUD-style API code.
- Separate repositories or services per role.

## Consequences

Positive:

- One build, one dependency set, easy local development, and the API and worker cannot drift in how they use the engine.
- The engine has no dependency on the web framework, and is tested directly against PostgreSQL.

Negative / known gaps:

- Dependencies are not role-specific: the worker image carries FastAPI and gunicorn, and the API image carries the handlers' HTTP client. `ruff` and `black` are not declared although linting is not configured at all.
- `src/api/health.py` imports the engine's `runtime` to read queue statistics; `src/engine/runtime.py` imports `src/shared/metrics.py`.
- The Dockerfile default `CMD` (`python -m src.api.main`) does nothing because `main.py` has no `__main__` block; every service relies on its compose `command`.
- The dev override starts the API with `--reload`, but the worker does not reload: restart it after editing code.
- No resource limits in compose.

## References

- `Dockerfile`, `docker-compose.yml`, `docker-compose.override.yml`, `pyproject.toml`
- `src/` tree, `docs/architecture.md`
- Related: ADR 0017, ADR 0018
