# 0022. Delete finished runs after a retention period

- Status: Accepted
- Date: 2026-10-10

## Context

Every run leaves one `workflow_instances` row (with its accumulated `data`) and one `workflow_step_executions` row per step attempt (with the data the step changed and any error text). Finished jobs are deleted by the engine (ADR 0018), but these rows were kept forever, so storage, indexes, listing queries and backups only grew. On the small servers this is meant to run on (`docs/scalability.md`) that ends in a full disk. The audit listed it as open work.

## Decision

The worker deletes finished runs once they are older than `RETENTION_DAYS`.

- **What goes.** Runs whose status is `completed`, `failed` or `cancelled` and whose `updated_at` is older than the period. A database trigger sets `updated_at` on every update, and a finished run is never updated again, so it is the finish time. Step executions and dead jobs go with the run (`ON DELETE CASCADE`).
- **What never goes.** A run that is `pending` or `running`, however old. A run waiting for an event for months is still a live run.
- **The setting.** `RETENTION_DAYS`, default 30. `0` turns retention off. Anything that is not a whole number of days (`-1`, `1.5`, `a month`, empty) makes the worker refuse to start rather than guess, because a wrong guess deletes data.
- **Who runs it.** A `Housekeeper` thread in every worker process (`src/engine/retention.py`): a first pass 60 seconds after start, then hourly. A pass deletes in batches of 500, oldest first, each batch its own short transaction with a short pause between, until nothing more is due. The selection uses `FOR UPDATE SKIP LOCKED`, so a row that a cancel or a finishing step holds is skipped, never waited for, and several workers can run passes at the same time without coordination. A failed pass is logged and retried on the next interval; it never stops the worker.
- **The index.** `idx_instances_finished`, a partial index on `updated_at` for finished runs only (`init.sql` and migration `003_retention_index.sql`), so finding what is due does not scan every run and running work does not pay for the index. A test checks that the real delete statement can use it.
- **Visibility.** The Prometheus counter `retention_deleted_total` and one log line per pass that deleted anything.

## Alternatives considered

- **Time-partitioned tables.** Dropping a partition is instant and leaves no dead rows, which matters at high volume. It needs the partition key in the primary keys and foreign keys and a job that creates partitions; more machinery than this size needs. Worth revisiting if deletes become a problem.
- **A separate scheduler container, or `pg_cron`.** Another process to run and monitor, and the extension is not in the `postgres:17-alpine` image. The worker already runs continuously and already talks to this database.
- **Different periods per status** (keep failed runs longer). Failed runs are the ones people investigate, so it is tempting, but one number is easier to explain and predict.
- **Off by default.** The safest choice for existing data, and a full disk months later is the cost of it. The default is on, with a long period, and the upgrade notes say so.
- **Archive or export before deleting.** Not built; backups are the only copy.

## Consequences

Positive:

- Growth is bounded by throughput times the period, with no extra process.
- Safe with several workers, and with a cancel or resume racing a delete.
- Deleting old runs also removes any secret that an earlier step put into the instance data.

Negative / follow-up:

- **Behaviour change on upgrade.** About a minute after the first worker starts with this version, every finished run older than 30 days is deleted. Set `RETENTION_DAYS` higher, or `0`, before upgrading if that history matters. Deleted history can only be recovered from a backup.
- Deleting rows leaves dead tuples. Autovacuum makes the space reusable, but the files do not shrink; use `pg_repack` or partitioning if a table grew large before retention was switched on.
- One period for every status, and whole runs only (no trimming of step data inside a kept run).
- Every worker process runs the housekeeper, so with several workers there are several passes an hour. This is harmless but redundant.
- A very large backlog is deleted at the speed of one batch per pass step (not measured). Nothing exposes how many runs are currently due.

## References

- `src/engine/retention.py`, `src/worker/main.py` (`RETENTION_DAYS`, `start_housekeeper`), `src/shared/metrics.py`
- `infrastructure/postgres/init.sql`, `infrastructure/postgres/migrations/003_retention_index.sql`
- `tests/integration/test_retention.py`, `tests/integration/test_retention_index.py`, `tests/unit/test_worker_main.py`
- Related: ADR 0017, ADR 0018, ADR 0014
