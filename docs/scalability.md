# Scalability

## Targets

| Target | Requirement |
|---|---|
| Throughput | 1,000 jobs per second |
| Scheduling latency | Jobs execute within 2 seconds of their scheduled time |

---

## Current Architecture Capacity

Before scaling, it helps to understand the throughput of each stage.

### Bottleneck Analysis

```
Trigger ingestion → Outbox write → Relay → RabbitMQ → Engine/Action Workers
       ①               ②           ③         ④               ⑤
```

| Stage | Bottleneck | Default capacity |
|---|---|---|
| ① API | CPU / connection pool | ~500–2,000 req/s per process |
| ② DB write (outbox) | IOPS / lock contention | ~1,000–5,000 rows/s per table |
| ③ Relay | Poll frequency × batch size | 100 msgs / poll cycle |
| ④ RabbitMQ | Message throughput | 50,000–100,000 msgs/s (single node) |
| ⑤ Workers | Number of workers × task duration | depends on action type |

At 1,000 jobs/second, the relay at 100 msgs/cycle needs to poll at least **10 times per second** to keep up. The default sleep between cycles must be ≤ 100ms.

---

## Scaling to 1,000 Jobs per Second

### 1. Scale the API Layer

The FastAPI server is stateless. Add replicas behind a load balancer:

```
Load Balancer (nginx / AWS ALB)
  ├─ api-1
  ├─ api-2
  └─ api-N
```

Each process handles webhook validation and DB writes. With async I/O (`asyncpg`) and a connection pool of 20–50 connections per instance, 4–8 API replicas handle 1,000 inbound triggers/second comfortably.

**PostgreSQL connection pooling:** use PgBouncer in transaction mode to multiplex many API connections over a smaller set of real DB connections.

### 2. Scale the Relay

The relay is the most sensitive bottleneck for throughput and latency:

```
relay-1  ─┐
relay-2  ─┼─► RabbitMQ
relay-N  ─┘
```

Each relay replica polls independently. `FOR UPDATE SKIP LOCKED` ensures no row is processed twice. To sustain 1,000 msgs/second:

```
required_relay_replicas = ceil(target_throughput / (batch_size / poll_interval_s))
                        = ceil(1000 / (100 / 0.05))   # 50ms poll interval
                        = ceil(1000 / 2000)
                        = 1  relay replica at 50ms polling
```

In practice, run 2–4 replicas for fault tolerance. Each adds throughput headroom.

**Tuning levers:**
- `RELAY_BATCH_SIZE` — increase to 500–1,000 if the relay is the bottleneck.
- `RELAY_POLL_INTERVAL_MS` — reduce to 50ms for higher throughput and lower latency.
- Relay replica count — scale horizontally as needed.

### 3. Scale the Orchestration Engine

The engine is a Celery consumer. Scale by adding workers:

```
docker-compose scale engine=8
```

Each engine worker uses a Redis lock per instance, so concurrent messages for *different* instances are fully parallel. Messages for the *same* instance are serialized by the lock (which is correct — you can't process STEP_COMPLETE before the instance finishes starting).

At 1,000 jobs/second with average orchestration task duration of 10ms, you need:

```
engine_workers = ceil(1000 jobs/s × 0.010 s/job) = 10 workers
```

Add 50% headroom → **15 engine workers**.

### 4. Scale the Action Workers

Action workers are independent of each other and of the engine:

```
docker-compose scale worker=32
```

Action duration is dominated by external API latency (Slack, GitHub). A typical HTTP call takes 200–500ms. At 1,000 actions/second:

```
action_workers = ceil(1000 × 0.350) = 350 workers
```

For 1,000 job/s with mostly action steps, you'll need hundreds of action workers. This is where **concurrency per worker process** matters:

- Use `--concurrency=4` (gevent) for I/O-bound handlers (HTTP calls).
- Use `--concurrency=1` (prefork) for CPU-bound handlers (Python execution).

With gevent and 4 concurrent tasks per worker, 90 worker processes handle 360 concurrent action tasks — sufficient for ~1,000 action/s at 350ms average latency.

### 5. Scale the Database

At 1,000 jobs/second, the `outbox` table sees:
- ~1,000 inserts/s (one per triggered workflow)
- ~1,000 updates/s (`processed_at`)
- Additional inserts from action results and step transitions

**Indexing:** the current schema has:

```sql
CREATE INDEX idx_outbox_unprocessed ON outbox (publish_at)
WHERE processed_at IS NULL;
```

This partial index is critical. Without it, every relay poll is a sequential scan.

**Outbox archival:** at 1,000 rows/s, the outbox table grows by 86M rows/day. Processed rows must be archived or deleted regularly:

```sql
-- Run via pg_cron or a background job every minute
DELETE FROM outbox
WHERE processed_at IS NOT NULL
  AND processed_at < NOW() - INTERVAL '1 hour';
```

**Read replicas:** route read-heavy queries (instance status, step history) to a read replica. The relay and workers only need the primary.

**Partitioning:** if the outbox or `workflow_step_executions` tables become very large, partition by `created_at` (monthly or daily range partitions) to keep vacuums and index scans fast.

### 6. Scale RabbitMQ

A single RabbitMQ node handles 50,000–100,000 msgs/s with small messages. At 1,000 jobs/s this is not a bottleneck. If it becomes one:
- Enable RabbitMQ clustering (3 nodes with quorum queues).
- Use lazy queues to move messages to disk and reduce memory pressure.

---

## Executing Jobs Within 2 Seconds of Scheduled Time

A job's "scheduled time" is the `publish_at` timestamp on the outbox row. The 2s latency budget covers:

```
publish_at  →  relay picks up row  →  RabbitMQ delivery  →  worker starts
                    Δ1                      Δ2                    Δ3
```

| Leg | Target | How to achieve |
|---|---|---|
| Δ1: relay polling lag | < 100ms | Poll interval ≤ 50ms, or use LISTEN/NOTIFY |
| Δ2: RabbitMQ queue wait | < 100ms | Ensure workers keep up with queue depth |
| Δ3: Worker startup / scheduling | < 200ms | `prefetch_multiplier=1`, enough workers |

With default 100ms polling and no queue backlog, average end-to-end latency is **50–400ms**. The 2s budget is met easily at low load.

**At high load (queue backlog)**, the 2s SLA requires:
1. Queue depth must stay near zero — add workers until `queue_depth / consumption_rate < 1s`.
2. Relay must not be the bottleneck — relay throughput must exceed message production rate.
3. Monitor `rabbitmq_queue_messages` and alert if depth exceeds 2,000 (at 1,000 msg/s this is 2s of backlog).

### LISTEN/NOTIFY for Sub-100ms Scheduling

For stricter latency (< 500ms from trigger to execution), add PostgreSQL LISTEN/NOTIFY to wake the relay immediately on outbox insert:

```sql
-- Trigger on outbox table
CREATE OR REPLACE FUNCTION notify_outbox()
RETURNS trigger AS $$
BEGIN
  PERFORM pg_notify('outbox_ready', '');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_notify_outbox
AFTER INSERT ON outbox
FOR EACH ROW EXECUTE FUNCTION notify_outbox();
```

```python
# Relay main loop
async def run():
    await conn.execute("LISTEN outbox_ready")
    while True:
        await conn.wait_for_notify(timeout=5.0)  # wake on notify or 5s timeout
        count = await relay_batch()
        if count == 0:
            await asyncio.sleep(0.01)  # tiny pause if nothing to do
```

This achieves < 10ms from outbox insert to relay pickup, while retaining the safety of the polling fallback for delayed messages.

### Monitoring Latency

Track these metrics to detect SLA violations:

```
outbox_relay_lag_seconds        — time from publish_at to relay pickup
queue_depth{queue="actions"}    — depth of actions_queue in RabbitMQ
celery_task_wait_seconds        — time task waits in queue before being picked up
step_execution_start_lag_seconds — time from step dispatch to worker start
```

Alert if `outbox_relay_lag_seconds p99 > 1.0` or `celery_task_wait_seconds p99 > 1.5`.

---

## Scaling Summary

| Component | Scale axis | Recommendation for 1k jobs/s |
|---|---|---|
| API server | Horizontal (replicas) | 4–8 replicas behind load balancer |
| Relay | Horizontal (replicas) | 2–4 replicas, 50ms poll interval |
| Engine workers | Horizontal (Celery workers) | ~15 workers |
| Action workers | Horizontal (Celery workers, gevent) | ~90 processes × 4 concurrency |
| PostgreSQL | Vertical + read replicas | Tune pool, add replica, partition outbox |
| RabbitMQ | Single node sufficient | Cluster at >50k msg/s |
| Redis | Single node sufficient | Cluster if lock contention detected |
