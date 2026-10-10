# Reliability: At-Least-Once Execution

## The promise

Every workflow that was accepted will run to a visible end (`completed`, `failed` or `cancelled`), and each step's result changes the instance's state **exactly once**, even when workers crash, hang or are restarted. A step's *side effects* (a Slack message, an HTTP call) can repeat after a crash, because no system can make an external call and a database commit atomic. That makes execution **at-least-once**.

For a workflow engine a lost job is worse than a repeated one, which can be made safe with idempotency keys.

---

## How it works

All state, including the queue, is in one PostgreSQL database, so the guarantees come from transactions and from one mechanism for crashes.

### 1. Starting is atomic

`start_instance` inserts the instance and its first job in one transaction. A crash before the commit leaves nothing; a crash after leaves a queued job. There is no window in which an instance exists with nothing scheduled.

### 2. Finishing a step is atomic

The step's result, the instance's new state and the next job are written in a single transaction (`finish_step`). A worker cannot save a result and forget to schedule what follows. Branches and delays are resolved inside the same transaction, so there is no half-advanced state to recover from.

### 3. Leases replace acknowledgements and sweepers

A worker takes a job by setting `locked_until` (default 300 s, `JOB_LEASE_SECONDS`). If the worker dies, the lease expires and the next worker's claim query picks the job up again. The same query serves new jobs, delayed jobs, retries and abandoned jobs. There is no separate recovery process.

### 4. Fencing keeps a stale worker harmless

A worker that is slow, not dead (a handler that outlives its lease) will eventually try to save its result. `finish_step` locks the instance row and checks the job is still `running` and still locked **by this worker**. If another worker has taken the job, the late result is discarded and nothing changes. The handler may have run twice, but the instance advances once.

### 5. Writers that are not workers use the same lock

Cancel and resume lock the instance row like a step does, so they queue behind a step that is finishing instead of racing it. A cancelled instance's in-flight step discards its result when it finishes.

### 6. Every failure ends visibly

| Situation | What happens |
|---|---|
| Handler returns a failure or raises | The attempt is recorded with the error text. If the step's `retry.max_attempts` allows, the same job is re-queued after `delay_seconds`; otherwise the job is marked `dead` and the instance `failed`. |
| Action id with no handler | Instance fails: `no handler registered for action '...'`. |
| `next` or branch target that does not exist | Refused when the workflow is saved ([ADR 0023](adr/0023-validate-workflow-definitions-when-they-are-saved.md)). In an older stored version the instance fails: `step '...' is not defined`. |
| Branch or delay cycle | Refused when the workflow is saved. In an older stored version, after 100 control steps in a row the instance fails. |
| Connection credential not found | Step fails before the handler runs. |
| `wait_for_event` times out | Instance fails: `wait step '...' timed out`. |
| Engine error (database hiccup) while processing a job | The job is released and retried after 10 s. |
| A step that keeps killing its worker | After `JOB_MAX_CLAIMS` (5) claims without finishing, the job is marked `dead` and the instance `failed`. |

Dead jobs stay in the `jobs` table for inspection (`SELECT ... FROM jobs WHERE status = 'dead'`) and are counted in `GET /health`.

---

## Failure scenarios

| Failure | What happens |
|---|---|
| API crashes before committing a start | Nothing was created; the caller got no instance id and can retry. |
| API crashes after committing | The job is queued; a worker runs it. |
| Worker crashes mid-step | Its lease expires; another worker claims the job. The handler may run again. |
| Worker is slow past its lease | Another worker takes over. When the slow one finishes, its result is discarded. |
| Worker is stopped (`SIGTERM`, `docker stop`) | It stops claiming, lets steps in flight finish (the compose grace period is 45 s), then exits. Anything cut short is recovered by lease expiry. |
| PostgreSQL restarts or is briefly unreachable | Workers log the error and retry every second; the dispatcher reconnects. No state is lost because none was held outside the database. |
| No worker is running | Jobs wait; `GET /health` turns unhealthy once a due job is older than `HEALTH_MAX_JOB_AGE_SECONDS` (30). |
| Handler hangs | It holds one thread until the call's own timeout. Threads cannot be killed, so a handler without a timeout can occupy a thread until the process restarts; the lease still lets another worker re-run the step. |

---

## What at-least-once does NOT mean

- **Not exactly-once side effects.** After a crash or a lease expiry a handler can run again, so Slack, GitHub, Trello, HTTP and SQL-execute steps can repeat. Use idempotency keys where the provider supports them, and write SQL so a repeat is harmless.
- **No heartbeat.** A step that legitimately runs longer than `JOB_LEASE_SECONDS` is run again by another worker. Set the lease above your slowest step.
- **Webhook deliveries are not de-duplicated.** GitHub redeliveries and Slack retries each start a new instance.
- **Durability follows PostgreSQL.** With the default `synchronous_commit` a committed start is on disk. Everything is in this one database, so back it up (`pg_dump`, or WAL archiving for point-in-time recovery). Losing the volume loses all workflows and history.
- **History is deleted after `RETENTION_DAYS` (default 30).** Finished runs and their step history are removed by a background thread in the worker; set `RETENTION_DAYS=0` to keep everything. Runs that have not finished are never removed. Back up the database if you may need older history ([ADR 0022](adr/0022-delete-finished-runs-after-a-retention-period.md)).

---

## Operating it

- Watch `GET /health`, the worker's metrics (`workflow_completed_total{status="failed"}`, `step_retry_total`) and the count of `dead` jobs.
- To rerun a failed instance, start a new one; instances are not resumable after failure.
- Tests that prove these properties: `tests/integration/test_engine.py` (crash recovery, stale-worker fencing, poison jobs, cancel during a step, retries, timeouts) and `tests/integration/test_worker.py` (parallelism, shutdown).
