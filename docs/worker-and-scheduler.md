# Worker and Scheduler

## Worker

### What the Worker Does

The action worker executes individual workflow steps. It is a Celery consumer of the `actions_queue`. It is completely stateless — all state lives in PostgreSQL — so any number of replicas can run in parallel.

**Entry point:** `src/worker/task.py`
**Business logic:** `src/worker/service.py`

### Execution Sequence

```
RabbitMQ: actions_queue
  │
  ▼
execute_action(message)          ← Celery task
  │
  ├─ Idempotency check           ← query workflow_step_executions
  │   (step already COMPLETED?)
  │
  ├─ Load instance.data from DB
  │
  ├─ Merge connection credentials
  │   (connections table → config override)
  │
  ├─ Registry lookup
  │   handler = registry.get(connector_id, action_id)
  │
  ├─ handler.execute(instance_id, data, config)
  │   returns ActionResult(status, updated_data, error_message)
  │
  └─ Write outbox row
      STEP_COMPLETE → orchestration_queue
      STEP_FAILED   → orchestration_queue
```

### Handler Registry

Handlers are registered with the `@action` decorator:

```python
# src/worker/registry.py
@action("slack_send_message")
class SlackSendMessageHandler:
    def execute(self, instance_id, data, config=None, **kwargs) -> ActionResult:
        ...
```

The registry maps `action_id` → handler instance. Handlers are imported at startup; adding a new connector means creating a new handler file and registering it.

### Celery Configuration

```python
task_ack_late = True              # ACK only after task completes
worker_prefetch_multiplier = 1    # One task at a time per worker thread
task_reject_on_worker_lost = True # Re-queue if worker dies mid-task
task_soft_time_limit = 300        # SIGTERM after 5 min (graceful)
task_time_limit = 360             # SIGKILL after 6 min (hard)
```

`task_ack_late = True` is the most important setting for reliability: the message is not removed from RabbitMQ until after the task function returns. If the worker crashes during execution, RabbitMQ re-delivers the message to another worker. Combined with the idempotency check, this gives at-least-once execution without double-execution side effects.

### Dead Letter Queues

Both `actions_queue` and `orchestration_queue` have a corresponding DLQ (`actions_dlq`, `orchestration_dlq`). Messages that exhaust Celery retries land in the DLQ for manual inspection.

---

## Scheduler (Relay Service)

### What "Scheduler" Means Here

There is no dedicated scheduler process in the traditional sense. Scheduled execution — both immediate dispatch and future/delayed steps — is implemented via the **Transactional Outbox pattern** combined with a polling **Relay Service**.

### Outbox Table

Every time the system needs to send a message (start a workflow, dispatch an action, schedule a retry, resume after a delay), it inserts a row into the `outbox` table **inside the same database transaction** as the state change:

```sql
-- Example: schedule a step to run 5 minutes from now
INSERT INTO outbox (destination, payload, publish_at)
VALUES ('orchestration_queue',
        '{"type": "STEP_COMPLETE", "instance_id": "..."}',
        NOW() + INTERVAL '300 seconds');
```

The `publish_at` column is how delayed execution works. A row with `publish_at` in the future is ignored by the relay until that time arrives.

### Relay Service — Current Implementation

**File:** `src/relay/service.py`

The relay runs in a tight loop (or with a short sleep between iterations):

```python
def relay_messages(self) -> int:
    rows = db.execute("""
        SELECT id, destination, payload
        FROM outbox
        WHERE processed_at IS NULL
          AND publish_at <= NOW()
        ORDER BY publish_at ASC
        LIMIT 100
        FOR UPDATE SKIP LOCKED
    """)

    for row in rows:
        task_name = TASK_ROUTING[row.destination]
        celery_app.send_task(task_name, kwargs=row.payload, ...)

    db.execute("UPDATE outbox SET processed_at = NOW() WHERE id = ANY(...)")
    return len(rows)
```

**Key properties:**
- `FOR UPDATE SKIP LOCKED` — rows locked by one relay replica are skipped by others, allowing safe horizontal scaling.
- Batch size of 100 — limits per-poll DB pressure.
- `publish_at <= NOW()` — the built-in delay mechanism; no separate scheduler needed for timed steps.

### How the Relay Discovers Jobs to Execute

**It polls.** Every iteration it queries PostgreSQL for unprocessed outbox rows due for delivery.

---

## Polling: Downsides and Alternatives

### Current Approach: Database Polling

```
Relay Service
  └─ every N ms: SELECT from outbox WHERE publish_at <= NOW()
```

**Pros:**
- Simple — one moving part.
- Transactional — the outbox row and the state change are atomic.
- Persistent — survives relay restarts without losing messages.
- No external dependency beyond PostgreSQL.

**Cons:**

| Problem | Detail |
|---|---|
| **Latency floor** | Minimum delivery latency ≈ poll interval. With 100ms polling, average latency is ~50ms; at 1s polling it's ~500ms. |
| **DB read pressure** | Every poll is a SELECT + UPDATE on the `outbox` table. At high message rates this adds significant read/write load. |
| **Thundering herd** | Multiple relay replicas all polling simultaneously can spike DB CPU even when the queue is empty. |
| **Tight loop risk** | If the relay loop has no sleep and the queue is always empty, it hammers the DB continuously. |
| **Coarse granularity** | Delays shorter than the poll interval (e.g. 1-second retries with 2-second polling) are rounded up. |

### Alternative Approaches

#### 1. Listen/Notify (PostgreSQL LISTEN/NOTIFY)

PostgreSQL has a built-in pub/sub mechanism. When a row is inserted into the outbox, a trigger fires `NOTIFY outbox_ready`. The relay holds an open connection and wakes up immediately on the notification.

```sql
-- Trigger fires on every INSERT into outbox
CREATE OR REPLACE FUNCTION notify_outbox_insert()
RETURNS trigger AS $$
BEGIN
  PERFORM pg_notify('outbox_ready', NEW.id::text);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_outbox_notify
AFTER INSERT ON outbox
FOR EACH ROW EXECUTE FUNCTION notify_outbox_insert();
```

```python
# Relay listens
conn.execute("LISTEN outbox_ready")
conn.poll()  # blocks until notification arrives
```

**Pros:** Near-zero latency for immediate messages; no unnecessary DB reads when idle.
**Cons:** Still need a fallback polling loop for delayed messages (`publish_at` in the future). NOTIFY does not carry the message content — the relay must still query for it.

**Best practice:** Use LISTEN/NOTIFY as a wake-up signal, fall back to polling every 5–10s for delayed messages and missed notifications.

#### 2. Dedicated Scheduling Service (e.g. pg_cron, APScheduler, Temporal)

Replace the outbox entirely with a purpose-built scheduler:

- **pg_cron** — PostgreSQL extension for cron-like jobs inside the DB.
- **APScheduler / Rocketry** — Python-native scheduler with persistent job stores.
- **Temporal / Conductor** — full workflow orchestration platforms with native scheduling.

These eliminate the relay entirely but introduce a new service dependency and operational complexity.

#### 3. Message Broker Native Delays

RabbitMQ supports **delayed message plugin** or **TTL + dead-letter routing**, which allow publishing a message with a delay natively in the broker. This removes the need for `outbox.publish_at` and the relay:

```python
# Publish with 5-second delay (requires rabbitmq_delayed_message_exchange plugin)
channel.basic_publish(
    exchange='delayed_exchange',
    routing_key='orchestration',
    body=payload,
    properties=pika.BasicProperties(
        headers={'x-delay': 5000}  # milliseconds
    )
)
```

**Pros:** True broker-side delays, no polling at all.
**Cons:** Loses the transactional guarantee — a crash between writing the instance and publishing the message can result in a lost job. Requires RabbitMQ plugin installation.

#### 4. Redis Sorted Sets (ZSet-based Scheduler)

Store jobs in a Redis sorted set keyed by their scheduled time (Unix timestamp as the score). A scheduler thread pops jobs whose score ≤ `NOW()`:

```python
# Schedule a job
redis.zadd("scheduled_jobs", {job_id: scheduled_timestamp})

# Poll
jobs = redis.zrangebyscore("scheduled_jobs", 0, time.time(), start=0, num=100)
```

**Pros:** Sub-millisecond poll latency, extremely fast for high-throughput scheduling.
**Cons:** Redis is not transactional with PostgreSQL — losing a Redis job means lost execution. Requires a separate durability strategy (Redis AOF + snapshots, or mirroring back to Postgres).

### Recommendation

The current outbox-polling approach is correct and sufficient for most loads. To improve it:

1. **Add LISTEN/NOTIFY** for immediate messages — reduces average latency from `poll_interval / 2` to near-zero without sacrificing durability.
2. **Keep polling as fallback** every 5–10 seconds for delayed messages and to catch any missed notifications.
3. **Tune poll interval** — for sub-second job latency targets, run the relay with a 50–100ms sleep between iterations.
4. **Scale relay horizontally** — `FOR UPDATE SKIP LOCKED` already makes this safe; run 2–4 replicas for throughput.

See [scalability.md](scalability.md) for throughput and latency targets.
