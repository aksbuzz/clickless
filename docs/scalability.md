# Scalability

What the system does today on small servers, what limits it, and how to tune it. Every number here was measured on the current code with the scripts in [`benchmarks/`](../benchmarks/); nothing is extrapolated unless it says so.

## Summary

| | About 1 vCPU / 2 GB | About 2 vCPU / 4 GB |
|---|---|---|
| Fast steps (transform, branch, log), Postgres and worker on the same box | 215 to 245 steps/s | 400 to 430 steps/s |
| Steps that wait 300 ms on an external API | about 90 steps/s with 32 threads, about 165 with 64 or more | not measured |
| Workflows started over HTTP | roughly 170 to 225 per second | roughly 225 to 265 per second |
| A 3-step workflow, start to finish, nothing else running | about 100 ms | |
| Memory for Postgres plus the worker | 80 to 120 MB | 100 to 145 MB |

"Servers of about 1 vCPU / 2 GB and 2 vCPU / 4 GB" are the usual sizes of the cheapest plans at common providers; check current pricing. The test machine is a laptop core, probably faster than a shared cloud vCPU, so expect less on rented hardware and **run the benchmarks on the server you plan to use** (below).

At 1 million steps a day (about 12 per second on average) either server is mostly idle. The target in the earlier version of this document, 1,000 jobs per second, is not reachable on one or two small cores: each step costs about 4 to 5 ms of CPU in total, so 1,000 steps per second needs on the order of 4 to 5 cores (an extrapolation from these figures, not a measurement) and a disk that can sync fast.

---

## Measurements

Method: PostgreSQL 17 and the Python workers run inside one container pinned to 1 or 2 CPUs (`docker run --cpuset-cpus`), on an Intel i5-1135G7 laptop under Docker Desktop, so the database and the workers compete for the same CPU, as they would on one small server. Single runs; expect noise of 15% or more. The disk-sync latency (`pg_test_fsync`) drifted between 2.5 ms and 9.4 ms per operation during the session, which moves the numbers for anything that commits (all of it). Workers used the default `synchronous_commit = on` unless the table says otherwise.

### Fast steps

Three internal steps per workflow (`transform_data`, `log`, `transform_data`). A "process x threads" worker runs that many steps at once.

| CPUs | Worker (processes x threads) | `synchronous_commit` | Steps/s | CPU busy | Worker CPU per step | PostgreSQL CPU per step |
|---|---|---|---|---|---|---|
| 1 | 1 x 1 | on | 73 | 37% | 1.4 ms | 3.7 ms |
| 1 | 1 x 4 | on | 143 | 61% | 1.1 ms | 3.1 ms |
| 1 | 1 x 8 | on | 217 | 84% | 1.0 ms | 2.9 ms |
| 1 | 1 x 16 | on | 245 | 92% | 0.9 ms | 2.9 ms |
| 1 | 1 x 8 | off | 285 | 94% | 0.8 ms | 2.5 ms |
| 2 | 1 x 8 | on | 299 | 64% | 1.2 ms | 3.1 ms |
| 2 | 1 x 16 | on | 414 | 89% | 1.1 ms | 3.2 ms |
| 2 | 2 x 8 | on | 397 | 88% | 1.2 ms | 3.3 ms |
| 2 | 2 x 8 | off | 431 | 93% | 1.1 ms | 3.2 ms |

Each step is about 3.1 database commits, 2.5 KB of WAL.

### Steps that wait on an external service

Every step waits 300 ms (a stand-in for a slow API call). 1 CPU.

| Threads | Steps/s | CPU busy |
|---|---|---|
| 8 | 25 | 16% |
| 32 | 89 | 46% |
| 64 | 169 | 82% |
| 128 | 123 | 69% |
| 256 | 164 | 91% |

With few threads throughput is `threads / latency` and the CPU is idle. Once there are enough threads the CPU is the limit again. 256 handler threads in one process add only about 20 MB.

### Starting workflows over HTTP

The real API (FastAPI, authentication, one transaction per start), a load generator on the same box.

| CPUs | uvicorn workers | `synchronous_commit` | Starts/s | API CPU per request | PostgreSQL CPU per request |
|---|---|---|---|---|---|
| 1 | 1 | off | 224 | 2.8 ms | 1.3 ms |
| 1 | 1 | on | 173 | 3.6 ms | 1.7 ms |
| 2 | 2 | off | 263 | 4.7 ms | 1.9 ms |
| 2 | 2 | on | 224 | 5.6 ms | 2.3 ms |

(`off` shows the CPU-bound rate; never use it for real starts, because an acknowledged request must be durable.) An earlier run of the same code on a quieter disk reached about 270 starts/s on one CPU.

---

## Where the time goes

- **PostgreSQL is the biggest consumer**: about 70% of the CPU per fast step. A step is roughly 15 statements in three short transactions (claim, begin, finish; counted from the code, not measured).
- **The worker is cheap**: 1 to 1.4 ms per step, less with more threads in one process.
- **The API is not the bottleneck.** Accepting a workflow costs about 3 to 4 ms of API CPU plus 1.5 ms of PostgreSQL, against about 12 ms to run its three steps.
- **Disk sync latency** matters at low concurrency (the box is mostly idle waiting for commits) and fades at high concurrency, where PostgreSQL batches commits.
- **Real integrations are limited by waiting, not CPU.** For steps that call out, throughput is `threads / latency`, so raise `WORKER_CONCURRENCY`. Also expect the provider's own rate limits (for example GitHub's per-token hourly limit, or about one message per second for a Slack incoming webhook; check current documentation) to cap you long before the server does. The handlers do not rate limit or honour `Retry-After` yet.

### What benchmarking found and fixed

Running these benchmarks on the real implementation exposed three problems, all now fixed and covered by tests:

1. **A `NOTIFY` per step serialised all commits.** PostgreSQL takes a global lock for every commit that issued `NOTIFY` and holds it through the disk sync, so throughput was capped near 80 steps/s however many threads ran. The worker that finishes a step now claims the next job itself and notifies nobody; only API starts, resumes, and jobs due in the future notify.
2. **The connection pool reopened a connection for almost every use.** `psycopg2` keeps at most `minconn` idle connections and closes the rest on return. The pool now keeps idle connections up to its maximum.
3. **Many threads exhausted the pool, and then PostgreSQL's connection limit.** Checkouts now wait for a free connection instead of failing, and the worker's pool is capped at 16 (`DB_POOL_MAX`), so `WORKER_CONCURRENCY=256` works with PostgreSQL's default of 100 connections.

---

## Sizing and tuning

| Setting | Default | Notes |
|---|---|---|
| `WORKER_CONCURRENCY` | 8 | Steps a worker process runs at once. Raise it for I/O-bound steps (threads are cheap); 16 saturated one CPU for fast steps. |
| `docker compose up --scale worker=N` | 1 | More worker processes. On one box, threads give nearly the same as processes; use more workers for more cores or more machines. |
| `JOB_LEASE_SECONDS` | 300 | Must exceed your slowest step, or the step is run again by another worker. |
| `DB_POOL_MAX` | `WORKER_CONCURRENCY + 2`, at most 16 (worker); 10 (API, per process) | Connections per process. Total across all processes must stay under PostgreSQL's `max_connections`. |
| `HEALTH_MAX_JOB_AGE_SECONDS` | 30 | How old a due job may get before `/health` reports no worker is taking jobs. |
| API workers | 4 (gunicorn) | About 180 MB for all four; two are enough on a 2 GB box. |

Memory of the whole four-container stack at rest, measured after the smoke test: api 178 MiB (four gunicorn workers), worker 28 MiB, PostgreSQL 46 MiB, frontend 10 MiB, about 260 MiB in total.

### PostgreSQL settings

The benchmarks above ran with PostgreSQL's defaults. [PGTune](https://pgtune.leopard.in.ua/) gives these starting points for PostgreSQL 17 on Linux, "online transaction processing", SSD storage, 50 connections, data smaller than RAM (they have not been benchmarked here):

| Setting | 1 vCPU / 2 GB | 2 vCPU / 4 GB |
|---|---|---|
| `shared_buffers` | 512MB | 1GB |
| `effective_cache_size` | 1536MB | 3GB |
| `maintenance_work_mem` | 128MB | 256MB |
| `work_mem` | 11750kB | 23501kB |

Same for both: `max_connections = 50`, `checkpoint_completion_target = 0.9`, `wal_buffers = 16MB`, `default_statistics_target = 100`, `random_page_cost = 1.1`, `effective_io_concurrency = 200`, `huge_pages = off`, `jit = off`, `wal_compression = lz4` (needs a PostgreSQL built with lz4), `min_wal_size = 2GB`, `max_wal_size = 8GB`. PGTune does not set autovacuum, `synchronous_commit` or `checkpoint_timeout`.

Housekeeping (from [Hatchet's PostgreSQL guide](https://hatchet.run/blog/postgres-survival-guide) unless noted; none of it is applied or measured here):

- Keep transactions short and never call external services inside one. The engine already holds no transaction while a handler runs.
- Tune autovacuum before bloat appears; the jobs and instance tables are updated constantly. Watch for autovacuum runs longer than about an hour in `pg_stat_activity`, and monitor transaction-id age for wraparound.
- Plan retention. `workflow_step_executions` and `workflow_instances` grow without bound (the `jobs` table does not: finished jobs are deleted). Time-based partitions make dropping old data instant.
- Use `pg_repack` rather than `VACUUM FULL` for bloat. Create indexes concurrently, and do not over-index.
- General practice, not from that guide: lower `fillfactor` on `workflow_instances` and `jobs` so updates can be HOT (an index on a frequently changed column such as `idx_instances_status` prevents that); and `LISTEN` needs a direct or session-pooled connection, so keep PgBouncer in transaction mode away from the worker's listener.

### Known limits

- Everything shares one PostgreSQL, so scaling out means scaling that one database up. A separate database server adds a network round trip to each of those roughly 15 statements, so on small plans keep it on the same machine.
- A step's handler cannot be killed. A hung handler holds a thread until its own timeout.
- Single-run measurements on a laptop; cloud vCPUs, networked disks and long soak runs were not measured.

---

## Reproducing the measurements

[`benchmarks/Dockerfile.bench`](../benchmarks/Dockerfile.bench) builds a one-container server with PostgreSQL and Python. From the repository root:

```bash
docker build -t clickless-bench -f benchmarks/Dockerfile.bench benchmarks
docker run -d --name vm-bench --cpuset-cpus=0 --memory=2g -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=workflows \
  -v "$PWD/infrastructure/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro" -v "$PWD:/repo:ro" clickless-bench
DSN=postgresql://postgres@127.0.0.1:5432/workflows
docker exec vm-bench python3 /repo/benchmarks/bench_steps.py --dsn $DSN --processes 1 --threads 8 --instances 600
docker exec vm-bench python3 /repo/benchmarks/bench_steps.py --dsn $DSN --threads 64 --io-latency-ms 300
docker exec vm-bench python3 /repo/benchmarks/bench_api.py --dsn $DSN --server-workers 1 --concurrency 32
docker update --cpuset-cpus 0,1 vm-bench      # emulate 2 CPUs
docker exec vm-bench pg_test_fsync -f /var/lib/postgresql/data/fsynctest -s 2    # disk sync latency
```

On Git Bash for Windows, prefix `docker` commands with `MSYS_NO_PATHCONV=1` and use Windows paths for the mounts. On a real server, run the two scripts directly against the database you will use; they report CPU split, commits, WAL and memory per step.
