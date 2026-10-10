# 0014. Schema management with a baseline `init.sql` and manual migrations

- Status: Accepted - under review (F-01 fixed on 2026-10-10 by folding migration 001 into `init.sql`; the process gap remains)
- Date: 2026-10-07 (recorded retrospectively)

## Context

The schema needs to exist before any service starts, including the seed workflow, and it evolves as features land (for example request-id tracing in commit `2f81df5`).

## Decision

- The baseline schema, trigger functions and a seed workflow live in `infrastructure/postgres/init.sql`, mounted into the Postgres container at `/docker-entrypoint-initdb.d/init.sql`. The Postgres image runs it only when the data directory is empty.
- Later changes are written as idempotent SQL files in `infrastructure/postgres/migrations/` (`001_add_request_id_tracing.sql` is the only one). Nothing mounts, runs or tracks them.
- The README's instruction for schema changes is to edit `init.sql` and run `docker-compose down -v`, which destroys the database volume.

## Alternatives considered

- A migration tool (Alembic, yoyo, Atlas, Flyway, sqitch) with a recorded schema version table.
- Run migrations from a one-shot compose service or init container that the API, engine, worker and relay wait on.
- Create tables from application code at startup.

## Consequences

Positive:

- Zero tooling; a fresh `docker compose up` gets a working schema and a demo workflow, as long as `init.sql` is complete.

Negative (F-01):

- `init.sql` was not updated when migration `001` was added. A freshly initialised database has no `request_id` column on `workflow_instances`, `workflow_step_executions` or `outbox`, yet the code writes and reads those columns (`src/api/repository.py` `create_instance`, `src/orchestration/adapters/postgres_unit_of_work.py`, `src/relay/service.py`). On a fresh install the first workflow start fails and the relay fails on every poll. Verified on 2026-10-10 by building a database from `init.sql` in a Postgres 17 container and running the API's INSERT and the relay's SELECT: both fail with `column "request_id" ... does not exist`.
- Existing environments only work if someone applied `001` by hand; there is no way to tell which migrations a given database has.
- Changing the schema in development means losing data (`down -v`), and there is no path for production upgrades.
- The outbox index in `init.sql` does not match its query (ADR 0002, F-13), and the seed data is applied on every fresh volume, including production-like ones.

Update 2026-10-10: `init.sql` now contains the `request_id` columns and indexes, and the same INSERT and SELECT succeed on a fresh database. The migration file is kept, annotated, for databases created earlier. The underlying gap (no tool that tracks which migrations a database has) is unchanged.

Direction: adopt a migration tool, fold `001` into the baseline or run it as migration 001, and add a startup or CI check that runs the migrations against an empty database and exercises one workflow.

## References

- `infrastructure/postgres/init.sql`, `infrastructure/postgres/migrations/`
- `docker-compose.yml` (postgres volumes), `README.md` ("Database changes")
- Related: ADR 0002, ADR 0013
