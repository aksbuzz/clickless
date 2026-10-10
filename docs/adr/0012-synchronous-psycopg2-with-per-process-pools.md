# 0012. Synchronous psycopg2 with small per-process pools

- Status: Accepted
- Date: 2026-10-07 (recorded after the fact; rewritten 2026-10-10 for the job-queue design)

## Context

The API and the worker both talk to PostgreSQL, and every state change must be transactional. The worker is thread-based and the API's route functions are synchronous, and the team wanted a small, explicit data layer.

## Decision

- Driver: `psycopg2` with `RealDictCursor`, raw SQL, no ORM.
- `src/shared/db.py`: one lazily created `ThreadedConnectionPool` per process, sized by `DB_POOL_MIN` / `DB_POOL_MAX` (defaults 1 and 10). The worker sets `DB_POOL_MAX` to `WORKER_CONCURRENCY + 2`, at most 16, unless it is set explicitly.
- **Idle connections are kept up to the maximum.** `psycopg2` otherwise keeps only `minconn` idle connections and closes the rest on return, which reconnects (a new backend process) on almost every use under load. `db.py` raises the retention limit after construction.
- **Checkouts wait.** A `BoundedSemaphore` sized to the pool makes `get_connection` wait up to 30 s for a free connection and then raise `PoolError`, instead of failing at once. A step holds a connection only for its three short transactions, so many threads share a small pool, and a high `WORKER_CONCURRENCY` cannot exceed PostgreSQL's `max_connections`.
- `db_cursor()` is a context manager that commits on success, rolls back on error and returns the connection.
- The engine's functions take a cursor (`src/engine/runtime.py`), so the caller chooses what shares a transaction: the API starts every matching workflow of a webhook in one transaction; the worker uses one transaction each to claim, begin and finish a step. **No transaction is open while a handler runs.**
- The worker's dispatcher holds one extra, dedicated `LISTEN` connection outside the pool.
- FastAPI route functions are plain `def` (run in the thread pool), with one exception, the external trigger webhook, which is `async def` (ADR 0009).

## Alternatives considered

- SQLAlchemy Core or ORM: migrations, typing and portability, at the cost of more machinery.
- `asyncpg` or psycopg 3 async: better per-process concurrency in the API; the worker's threads would not benefit.
- PgBouncer in front of PostgreSQL: lets many processes share few connections; not used, and it must not sit in transaction mode in front of the `LISTEN` connection.

## Consequences

Positive:

- Simple, explicit SQL; transactions are easy to reason about, and short.
- Connection use no longer depends on handler duration; the connection budget is the sum of per-process pool maxima (API: 4 workers x 10, worker: up to 16).
- Measured effect of the pool changes is in `docs/scalability.md`.

Negative / known gaps:

- The blocking calls in the `async def` trigger route stall the event loop of that gunicorn worker while they run.
- Unique-violation handling matches the string "unique" in the exception text (`src/api/service.py`), which is brittle.
- No query timeouts or `statement_timeout` are configured.
- Each API request costs a connection from a pool of at most 10 per process; heavy API concurrency waits for connections.

## References

- `src/shared/db.py`, `src/shared/base_repository.py`
- `src/engine/runtime.py`, `src/engine/worker.py`
- `tests/unit/test_db_pool.py`, `tests/integration/test_db_pool_reuse.py`
- Related: ADR 0018
