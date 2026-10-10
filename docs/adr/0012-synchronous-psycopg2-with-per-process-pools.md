# 0012. Synchronous psycopg2 with per-process connection pools

- Status: Accepted - under review (known gaps: F-14, F-16)
- Date: 2026-10-07 (recorded retrospectively)

## Context

Every process (API, relay, engine, worker) talks to PostgreSQL, and every state change must be transactional (ADR 0002). Celery workers and Celery tasks are synchronous by nature, and the team wanted a small, explicit data layer. Commit `03c71a2` ("fix db pool issue") shows pool sizing already caused trouble.

## Decision

- Driver: `psycopg2` with `RealDictCursor`, raw SQL, no ORM.
- `src/shared/db.py`: one lazily created `ThreadedConnectionPool(minconn=5, maxconn=20)` per process; `get_connection` retries up to 10 times at 100 ms when the pool is exhausted; `db_cursor()` is a context manager that commits on success, rolls back on error and returns the connection.
- `BaseRepository` offers thin `fetch_one` / `fetch_all` / `execute` helpers; `BasePostgresUnitOfWork` (thread-local connection and cursor) is used by the orchestrator so several repository calls share one transaction.
- FastAPI route functions are plain `def` (run in the thread pool), with one exception, the external trigger webhook, which is `async def` (see ADR 0009).

## Alternatives considered

- SQLAlchemy Core or ORM: migrations, typing and portability, at the cost of more machinery and its own pooling to tune.
- `asyncpg` or psycopg 3 async in the API: better per-process concurrency; `docs/scalability.md` assumes `asyncpg`, but the code does not use it. It would not help Celery workers.
- PgBouncer in transaction mode in front of Postgres: also assumed by the docs, not present in compose.

## Consequences

Positive:

- Simple, explicit SQL; easy to read and reason about transactions.
- No async/sync impedance in Celery tasks.

Negative / known gaps:

- Connection budget is multiplicative and unmanaged (F-14). Each process can hold up to 20 connections and opens 5 immediately on first use. With 4 gunicorn workers, an engine, two action workers and a relay, and Celery's default prefork concurrency (CPU count) per Celery process, the total can exceed PostgreSQL's default `max_connections` of 100. Neither `--concurrency` nor `max_connections` is set anywhere.
- The action worker holds a connection and an open transaction for the entire duration of a handler call, up to the 300 s soft limit (F-16). The relay likewise keeps its transaction open while publishing a batch. Idle-in-transaction sessions block vacuum and consume pool slots.
- The blocking calls in the `async def` trigger route stall the event loop of that gunicorn worker (F-18).
- Unique-violation handling is done by matching the string "unique" in the exception text (`service.py`), which is brittle (F-20).
- No query timeouts or `statement_timeout` are configured.

## References

- `src/shared/db.py`, `src/shared/base_repository.py`, `src/shared/base_unit_of_work.py`
- `src/orchestration/adapters/postgres_unit_of_work.py`
- `docs/scalability.md`
- Related: ADR 0002, ADR 0006
