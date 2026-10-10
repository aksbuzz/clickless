# Worker and Scheduler

## There is no separate scheduler

The worker takes jobs from PostgreSQL, and a job's `run_at` says when it may run. Starting a run, retrying a failed step, waiting out a `delay`, and timing out a `wait_for_event` are all just jobs with a `run_at`. A job with `run_at` in the future is simply not claimable until then.

## The worker process

Entry point `src/worker/main.py`, logic in `src/engine/worker.py`.

```
worker process
├── dispatcher thread      holds the one LISTEN connection; wakes runners
├── step-runner thread x N  each: claim -> begin -> run handler -> finish -> repeat
└── metrics server          Prometheus on port 9100
```

- **Runner threads** (`WORKER_CONCURRENCY`, default 8) share a small connection pool. A thread needs a database connection only for the three short transactions of a step, never while the handler runs, so many threads can wait on slow external calls at once. If every connection is busy, a thread waits for one (up to 30 s).
- **The dispatcher** keeps a single `LISTEN` connection for the whole process. Each time it wakes it asks the database how long until the next job is due or the next lease expires, and sleeps until then (at most 1 s, so it notices a shutdown request). When a job is due it wakes one idle runner.
- **`WakeSignal`** hands out wake-ups so none is lost between "nothing to do" and "going to sleep". A runner that finishes a job wakes one more, so a burst of jobs spreads across idle threads without every thread polling.
- Every wake-up is only a hint. The truth is the claim query: if nothing is due it returns nothing and the thread sleeps again.

### Why not poll, and why not `NOTIFY` for everything

Polling alone adds latency equal to the poll interval to every job. `NOTIFY` alone cannot express "wake me in 30 seconds", and it has a cost: PostgreSQL takes a global lock for every commit that issued `NOTIFY` and holds it through the disk sync, so a `NOTIFY` per step capped the whole system near 80 steps per second (found by benchmarking; see [scalability.md](scalability.md)). The worker therefore combines both:

| Event | Notifies? | Why |
|---|---|---|
| API starts a workflow | yes | Idle workers must start it now. |
| `POST /instances/{id}/events` resumes a waiting step | yes | Same. |
| A step finishes and the next job is due immediately | **no** | The same thread claims it on its next loop. |
| A job is queued for later (delay, retry back-off, wait timeout) | yes | A sleeping dispatcher may need an earlier deadline. |
| Nothing happens | no | A safety wake every `WORKER_IDLE_POLL_SECONDS` (default 5) covers a missed notification. |

A job due in 30 seconds is claimed within about 50 ms of becoming due, without any polling in between. `LISTEN` needs a direct or session-pooled connection, so keep PgBouncer in transaction mode away from it.

## Time-based behaviour

- **Delay.** `delay` steps are resolved while finishing the previous step: the duration is added to the next job's `run_at`. No job exists for the delay itself, and nothing runs or holds a lease while an instance waits.
- **Retry.** A failed attempt with attempts left updates the same job: `run_at = now + retry.delay_seconds`, claim count reset.
- **Wait timeout.** Arming a `wait_for_event` step queues a `wait_timeout` job for `timeout_seconds` later. Resuming the instance deletes it. If it fires while the instance is still waiting, the instance fails.
- **Lease expiry.** A running job whose `locked_until` has passed is claimable again; that is how work from a crashed worker returns to the queue.

## Shutdown

`SIGTERM` or `SIGINT` sets a stop flag. Runner threads finish the step they are in, then exit; the dispatcher stops on its next tick; the pool is closed. `docker compose` waits 45 s (`stop_grace_period`). A step still running at that point is recovered by lease expiry.

## Connector handlers

A handler is a class registered with `@action("action_id")` (`src/worker/registry.py`); the engine finds it by the step's `action_id`.

```python
@action("my_action")
class MyHandler:
    untemplated_keys = ()          # config keys the engine must NOT resolve {{templates}} in

    def execute(self, instance_id, data, config=None, **kwargs) -> ActionResult:
        ...
        return ActionResult(ActionStatus.SUCCESS, data)       # or FAILURE with error_message
```

- `config` arrives with `{{templates}}` already resolved, and with the step's stored connection merged in (the step's own keys win). Do not resolve templates again.
- `data` is a copy of the instance data. Return the full dict you want the instance to have; the engine stores only what changed, and removes keys you removed.
- Handlers run concurrently on different threads and must be stateless. They do not touch the database; the engine does that around them.
- Anything that connects out for the workflow author must pass through `src/shared/net_guard.py`.
- Raise or return a failure for any problem; the engine records the message and applies the step's retry policy.

## Metrics

The worker serves Prometheus metrics on `WORKER_METRICS_PORT` (default 9100, inside the compose network): `workflow_started_total`, `workflow_completed_total`, `workflow_duration_seconds`, `workflow_errors_total`, `step_execution_total`, `step_duration_seconds`, `step_retry_total`. The API serves its own HTTP metrics at `/metrics`.
