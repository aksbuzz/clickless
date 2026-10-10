# Spike: Postgres-only workflow runtime

A working proof of the design proposed in [ADR 0017](../../docs/adr/0017-postgres-backed-job-queue-replaces-outbox-broker-and-celery.md) and [ADR 0018](../../docs/adr/0018-one-job-per-step-with-lease-fencing-and-single-transaction-advance.md). It is not wired into the API and nothing in `src/` was changed.

It replaces the outbox, relay, RabbitMQ, Celery, the engine/worker split, the Redis lock and the recovery sweeper with one `jobs` table and one worker loop. It reuses the real connector handlers from `src/worker/handlers/`, the template helper from `src/shared/connectors/template.py`, and the existing tables from `infrastructure/postgres/init.sql` (including the seed workflow).

| File | What it is |
|---|---|
| `schema.sql` | the `jobs` table and its indexes |
| `pg_engine.py` | claim loop, lease and fencing, step advance, retry, delay, wait/event, cancel (about 430 lines) |
| `test_spike.py` | 20 tests against a real PostgreSQL |
| `conftest.py` | connects to Postgres, applies `schema.sql`, cleans tables between tests |

## Run it

Needs Docker and Python 3.12 or newer. The database is a throwaway container on localhost with the project's own `init.sql`, no password, not reachable from other machines.

```bash
docker run -d --name clickless-spike-pg -p 127.0.0.1:55432:5432 \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=spike \
  -v "$(pwd)/infrastructure/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro" \
  postgres:17-alpine
```

Run that from the repository root (in Git Bash on Windows, prefix it with `MSYS_NO_PATHCONV=1` and write the `init.sql` mount as a Windows path like `E:\...`), then, from `spikes/pg-queue/`:

```bash
python -m venv .venv && . .venv/bin/activate      # on Windows: .venv\Scripts\activate
pip install psycopg2-binary structlog httpx pytest
pytest -q
```

Tests skip with a message if no database answers at `SPIKE_DSN` (default `postgresql://postgres@127.0.0.1:55432/spike`). Remove the database with `docker rm -f clickless-spike-pg`.

Throughput test knobs: `SPIKE_WORKERS` (default 4), `SPIKE_INSTANCES` (default 300), run with `pytest -s -k many_instances`.

## What the tests show

Results on 2026-10-10: **20 passed**, PostgreSQL 17, Python 3.14.

- Seed `order_priority_workflow` runs to completion with the real `python_execute`, `transform_data` and `log` handlers, for both branches.
- Crash recovery: a job claimed by a worker that never finishes is taken by another worker once the lease expires.
- Zombie worker: a worker whose lease expired and whose job was reclaimed finishes later; its result is discarded. The handler ran twice, state advanced once.
- A job claimed more than `MAX_CLAIMS` times is marked `dead` and its instance failed.
- Cancel during a running step: the result is discarded, the next step never starts.
- Retry policy: success after failures, and exhaustion with the last error recorded.
- Delay: implemented as a future `run_at`; workers sleep until it is due (no fixed polling interval); measured gap between steps was between 1 s and 2 s for a 1 s delay.
- `wait_for_event`: resumes on an event (and cancels its timeout job), or fails on timeout. An event for an instance that is not waiting is rejected.
- Failure paths that strand instances today now fail with a reason: unknown action, dangling `next`, missing connection, branch cycle.
- Templates (`{{...}}`) are resolved for every handler in one place; step output stores only the keys the step changed; keys a step removes are removed.
- 300 instances of a 3-step workflow across 4 workers: every step completed exactly once.

## Benchmarks: what limits throughput on a small server

`bench.py` (step execution) and `bench_api.py` (HTTP ingestion) report steps/s and requests/s together with the CPU spent per step by the worker processes and by PostgreSQL, plus commits, WAL and memory. They are meant to be run on the machine you intend to rent.

To emulate a small server on a larger machine, `Dockerfile.bench` builds one container that holds PostgreSQL and Python, so both share the CPU you give it:

```bash
docker build -t clickless-bench -f spikes/pg-queue/Dockerfile.bench spikes/pg-queue
docker run -d --name vm-bench --cpuset-cpus=0 --memory=2g -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=spike \
  -v "<repo>/infrastructure/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro" -v "<repo>:/repo:ro" clickless-bench
DSN=postgresql://postgres@127.0.0.1:5432/spike
docker exec vm-bench python3 /repo/spikes/pg-queue/bench.py --dsn $DSN --workers 4 --instances 600
docker exec vm-bench python3 /repo/spikes/pg-queue/bench_api.py --dsn $DSN --server-workers 1 --concurrency 32
docker update --cpuset-cpus 0,1 vm-bench      # now emulate 2 CPUs
```

Results below were taken on 2026-10-10 on an Intel i5-1135G7 laptop (Docker Desktop, Windows), with the container pinned to 1 or 2 CPUs. Single runs; expect noise of at least 15%. A cloud vCPU is usually slower than this laptop core, so treat the absolute numbers as an upper bound and re-run both scripts on the real VM.

**Step execution** (3 internal steps per workflow, one job at a time per worker process):

| CPUs | Workers | `synchronous_commit` | Steps/s | CPU busy | Worker CPU ms/step | Postgres CPU ms/step | Commits/step |
|---|---|---|---|---|---|---|---|
| 1 | 1 | on | 64 | 33% | 1.37 | 3.85 | 3.7 |
| 1 | 2 | on | 80 | 43% | 1.44 | 3.92 | 4.4 |
| 1 | 4 | on | 156 | 73% | 1.34 | 3.34 | 5.7 |
| 1 | 8 | on | 152 | 93% | 1.84 | 4.27 | 8.4 |
| 1 | 4 | off | 199 | 98% | 1.49 | 3.44 | 5.5 |
| 2 | 2 | on | 124 | 39% | 1.77 | 4.49 | 4.4 |
| 2 | 4 | on | 184 | 60% | 1.83 | 4.72 | 5.7 |
| 2 | 8 | on | 220 | 77% | 1.98 | 4.99 | 8.4 |
| 2 | 16 | on | 154 | 60% | 2.16 | 5.63 | 13.7 |
| 2 | 8 | off | 291 | 98% | 1.88 | 4.86 | 8.1 |

**HTTP ingestion** (FastAPI + uvicorn + `start_workflow`, one commit per request, load generator on the same machine):

| CPUs | uvicorn workers | Concurrency | Requests/s | API CPU ms/request | Postgres CPU ms/request |
|---|---|---|---|---|---|
| 1 | 1 | 1 | 180 | 1.33 | 1.11 |
| 1 | 1 | 8 | 297 | 1.23 | 0.98 |
| 1 | 1 | 32 | 255 | 1.29 | 1.04 |
| 2 | 2 | 32 | 368 | 1.56 | 1.14 |

(A 2-CPU run at concurrency 8 gave 149 requests/s for reasons I did not investigate, which is why single runs should not be over-read.)

**Memory:** PostgreSQL plus the workers used 70 MB with 1 worker, 144 MB with 4, 242 MB with 8 and 441 MB with 16, about 25 MB for each extra worker process (including its two database connections).

What this says:

- PostgreSQL, not Python, is the heaviest consumer: about 70% of the CPU per step, against about 1.4 to 2 ms for the worker. At low concurrency the box is mostly idle and waiting for commits (fsync); with enough workers it becomes CPU bound.
- The HTTP layer is not the bottleneck: about 1.3 ms of API CPU plus 1 ms of Postgres per accepted workflow, against roughly 15 ms to run its three steps.
- This spike wastes work as workers are added: commits per step rise from 3.7 to 13.7 because idle workers poll and every `NOTIFY` wakes all of them, and throughput falls at 16 workers. That is fixable (see ADR 0017).
- Doubling the CPUs gave 40 to 45% more throughput, not 2x, for the same reasons.
- `synchronous_commit=off` gave 30 to 40% more steps/s. It must not be used for the ingestion path, because an acknowledged webhook could be lost in a crash.

## What the spike does not do

- No HTTP API, webhook ingestion, authentication, connection secrets handling, request-id propagation or metrics.
- No purge of finished jobs, and no lease heartbeat (a handler longer than the lease is run again).
- No definition validation beyond catching undefined steps and branch/delay cycles at run time.
- The security problems in the Python, SQL and HTTP handlers (audit F-02, F-05, F-06) are unchanged: the seed workflow still runs `python_execute`. Run it only on a trusted machine with trusted data.
- Frontend not checked: step executions are now one row per attempt and `input_data` is empty.

## Optimisation backlog (noted, deliberately not done)

Decided on 2026-10-10: the spike stays as measured above. These are the known improvements, in rough order of expected value. Items marked (measured) have evidence in this directory; the rest are hypotheses to test with `bench.py` and `bench_api.py`.

**Wasted work in the worker loop**
1. (measured) Commits per step grow from 3.7 to 13.7 as workers are added: idle workers poll, and every `NOTIFY` wakes all of them, each running an empty claim transaction. Throughput drops at 16 workers on 2 CPUs. Options: one listener per process feeding in-process workers, jittered back-off for idle workers, and running the read-only "when is the next job due" query in autocommit instead of its own transaction.
2. Merge the claim and begin transactions (3 write commits per step down to 2), and drop redundant statements: the instance row is updated two to three times per step and its `updated_at` trigger fires each time.
3. Claim in batches for fast steps. The Hatchet guide's claim statement takes up to 100 tasks in one `FOR UPDATE SKIP LOCKED` CTE, and it reports about 10x from batching writes in one round trip.
4. (measured, +30 to 40%) `synchronous_commit=off` for worker connections only. Never on the ingestion path: an acknowledged webhook must be durable.

**Concurrency for real integrations**
5. Run handlers on threads or async tasks that share a small database pool and a single listener. Today each in-flight handler costs about 25 MB (a process and two connections), which is the limit on a small box. No transaction is held during a handler, so this is possible without redesign.
6. Reuse one HTTP client per connector instead of `httpx.post` per call (new connection and TLS handshake each time), and add per-connection rate limiting with `429` / `Retry-After` handling. Third-party limits will cap throughput long before the database does.

**PostgreSQL housekeeping** (from the Hatchet "Postgres survival guide", https://hatchet.run/blog/postgres-survival-guide, unless marked)
- Keep transactions short and never call external services inside one. The spike already holds none during a handler.
- Avoid row-by-row deletes of historical task data; partition by time and drop partitions. This applies to finished `jobs` and to `workflow_step_executions`.
- Tune autovacuum before bloat appears. The guide gives no values; it points to Cybertec's autovacuum tuning article. It suggests investigating any autovacuum that runs longer than about an hour in `pg_stat_activity`, and monitoring transaction-id usage for wraparound.
- Use `pg_repack` rather than `VACUUM FULL` for bloat, and `REINDEX INDEX CONCURRENTLY` for indexes. Create indexes concurrently, and do not over-index.
- Avoid connection storms and keep connections long-lived; use PgBouncer or an in-process pool.
- Not covered by that guide, so general practice and unmeasured here: set a lower `fillfactor` on `workflow_instances` and `jobs` so updates can be HOT (the instance row is updated several times per step, and an index on a frequently changed column such as `idx_instances_status` prevents HOT updates); `LISTEN/NOTIFY` is reported to take a global lock at commit, which can limit many concurrent writers that notify (check before relying on it at high rates); `LISTEN` needs a direct or session-pooled connection, not PgBouncer transaction mode.

**Starting `postgresql.conf` for the two VM sizes** (from https://pgtune.leopard.in.ua/ with PostgreSQL 17, Linux, DB type OLTP, SSD storage, 50 connections, data size less than RAM). PGTune covers memory, planner and WAL sizing only. It does not set autovacuum, `synchronous_commit` or `checkpoint_timeout`, and `wal_compression = lz4` needs a PostgreSQL built with lz4.

| Setting | 1 vCPU / 2 GB | 2 vCPU / 4 GB |
|---|---|---|
| `shared_buffers` | 512MB | 1GB |
| `effective_cache_size` | 1536MB | 3GB |
| `maintenance_work_mem` | 128MB | 256MB |
| `work_mem` | 11750kB | 23501kB |

Same for both: `max_connections = 50`, `checkpoint_completion_target = 0.9`, `wal_buffers = 16MB`, `default_statistics_target = 100`, `random_page_cost = 1.1`, `effective_io_concurrency = 200`, `huge_pages = off`, `jit = off`, `wal_compression = lz4`, `min_wal_size = 2GB`, `max_wal_size = 8GB`.

The benchmarks above ran with PostgreSQL's defaults, not with these settings, so applying them is another thing to measure.
