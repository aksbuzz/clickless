# 0014. Schema management with a baseline `init.sql` and numbered migrations

- Status: Accepted - under review (known gap: nothing records which migrations a database has had)
- Date: 2026-10-07 (recorded after the fact; rewritten 2026-10-10)

## Context

The schema needs to exist before any service starts, including the seed workflow, and it evolves as features land.

## Decision

- The baseline schema, trigger functions and a seed workflow live in `infrastructure/postgres/init.sql`, mounted into the Postgres container at `/docker-entrypoint-initdb.d/init.sql`. The Postgres image runs it only when the data directory is empty.
- Changes for databases that already exist are idempotent SQL files in `infrastructure/postgres/migrations/`, applied by hand (`README.md` shows the command). Today: `001_add_request_id_tracing.sql` (adds `request_id` columns; its outbox part is skipped when the outbox is gone) and `002_job_queue.sql` (creates `jobs`, turns unfinished instances into jobs, drops `outbox` and the unused `input_data` column).
- `init.sql` must produce the same schema as the baseline plus every migration. `tests/integration/test_migration_job_queue.py` enforces that: it builds a database from a snapshot of the previous schema, applies the migration, and compares tables, columns and indexes with a fresh `init.sql` database. It also checks that unfinished instances become jobs and that the migrations run twice or in order without error.
- The integration tests build their database from the real `init.sql` (`tests/integration/conftest.py`), so a broken baseline fails the suite, and CI runs the stack from a fresh volume (`scripts/smoke.sh`).

## Alternatives considered

- A migration tool (Alembic, yoyo, Atlas, Flyway, sqitch) with a recorded schema version table.
- Run migrations from a one-shot compose service that the other services wait for.
- Create tables from application code at startup.

## Consequences

Positive:

- Zero tooling; a fresh `docker compose up` gets a working schema and a demo workflow.
- The upgrade path is tested against the real previous schema.

Negative / known gaps:

- There is no table recording applied migrations, so only convention says which a database has had; migrations must stay idempotent.
- Migrations are applied by hand and need the stack stopped; there is no automatic or online upgrade.
- Changing the schema in development with `docker compose down -v` loses the data.
- The seed workflow is created on every fresh volume, including production-like ones.
- No retention: `workflow_instances` and `workflow_step_executions` grow without bound.

## References

- `infrastructure/postgres/init.sql`, `infrastructure/postgres/migrations/`
- `tests/integration/conftest.py`, `tests/integration/test_migration_job_queue.py`, `tests/integration/schema_before_job_queue.sql`
- `README.md` ("Database changes")
- Related: ADR 0017
