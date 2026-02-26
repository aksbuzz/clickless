# Reliability: At-Least-Once Execution

## The Problem

Distributed systems can fail at any point:
- The API server crashes after creating an instance but before sending a message to RabbitMQ.
- A worker dies mid-execution.
- RabbitMQ loses a message before the consumer ACKs it.
- The database is temporarily unreachable.

For a workflow system, a lost job is worse than a duplicate job (which can be made safe with idempotency). The system is designed to guarantee **at-least-once execution**: every scheduled job will eventually run, even in the face of partial failures.

---

## Guarantee 1: Transactional Outbox

**The core invariant:** a workflow instance and its dispatch message are always created together atomically, or not at all.

```python
# src/api/service.py — trigger handling
with db.transaction():
    instance_id = repo.create_instance(workflow_version_id, trigger_data)
    repo.schedule_outbox_message(
        destination="orchestration_queue",
        payload={"type": "START_WORKFLOW", "instance_id": instance_id},
        publish_at=None,  # immediately
    )
```

If the server crashes after the `INSERT workflow_instances` but before the `INSERT outbox`, the transaction rolls back and neither row exists — no zombie instance with no dispatch message.

If the server crashes after both inserts but before the relay sends the message, the outbox row remains `processed_at IS NULL` and the relay will pick it up on the next poll.

**This is the single most important reliability mechanism in the system.**

---

## Guarantee 2: Late ACK in Celery

RabbitMQ delivers a message to a Celery worker. By default Celery ACKs the message when it is received. With `task_ack_late = True` (configured in `src/shared/celery_app.py`), the ACK is sent only after the task function returns successfully.

```
Worker receives message from RabbitMQ
  │
  ├─ [task_ack_early = True (default)]
  │   ACK sent immediately → message deleted from queue
  │   Worker crashes → message is LOST
  │
  └─ [task_ack_late = True (current config)]
      ACK sent after task completes → message stays in queue until done
      Worker crashes → RabbitMQ re-delivers to another worker ✓
```

Combined with `task_reject_on_worker_lost = True`, if a worker process dies unexpectedly, its unACKed messages are immediately returned to the queue rather than waiting for a timeout.

---

## Guarantee 3: Idempotent Action Execution

Because the system uses at-least-once delivery (not exactly-once), any step could be executed more than once. The worker guards against this with an idempotency check:

```python
# src/worker/service.py
existing = repo.get_step_execution(instance_id, step_name)
if existing and existing.status == "completed":
    logger.info("step already completed, skipping", ...)
    return  # Do nothing — result already in instance.data
```

`workflow_step_executions` acts as a deduplication log. If a retry delivers the same action twice, the second execution is a no-op.

**Limitation:** handlers that call external APIs (Slack, GitHub) are not inherently idempotent — a duplicate execution could send two Slack messages. Fully idempotent external calls require:
- Idempotency keys on API calls where the external service supports them.
- Storing the result of the first call and returning it on duplicates.

This is the boundary of what the framework can guarantee; connector implementors must design handlers to be safe under re-delivery.

---

## Guarantee 4: Celery Automatic Retries

Transient failures (network timeouts, database connection drops) are retried automatically by Celery up to 3 times with exponential backoff before the message is routed to the DLQ.

User-defined retry logic (`"retry": {"max_attempts": 3, "delay_seconds": 5}` in the workflow definition) operates at a higher level — it retries the entire step via the outbox, not the Celery task itself.

---

## Guarantee 5: Stuck Instance Recovery

The `engine.recover_stuck` Celery Beat task runs every 30 seconds:

```python
# src/orchestration/entrypoint/celery_task.py
@app.task(name="engine.recover_stuck")
def recover_stuck():
    # Find instances in status=running with no activity for > threshold
    # Re-enqueue a START or STEP event
    ...
```

This catches edge cases where:
- The relay relayed the message but the engine worker crashed before processing it.
- A Redis lock expired without being released, and the event was dropped.
- The orchestration event was ACKed but the outbox write at the end failed.

The sweeper provides a safety net with a bounded detection latency of 30 seconds.

---

## Failure Scenarios

| Failure | Detection | Recovery |
|---|---|---|
| API crashes before outbox write | Transaction rollback | No orphan instance; trigger webhook re-fires or user retries |
| Relay crashes before sending to RabbitMQ | `processed_at IS NULL` | Next relay poll picks it up |
| Engine worker crashes mid-task | `task_ack_late` + RabbitMQ re-delivery | Task re-executed on another worker |
| Engine writes state but crashes before outbox | Stuck instance | Recovery sweeper re-enqueues within 30s |
| Action worker crashes mid-task | `task_ack_late` + RabbitMQ re-delivery | Action retried; idempotency check prevents double execution |
| Redis lock expires during processing | N/A | Next event delivery succeeds (lock gone); state machine guards against stale events |

---

## What At-Least-Once Does NOT Mean

- **Not exactly-once delivery.** The same Celery task may run twice. The idempotency check handles this for actions; orchestration events are idempotent by design (stale-event guards).
- **Not zero data loss under all conditions.** If PostgreSQL loses committed data (e.g. unplanned `DROP TABLE`), all state is gone. This is mitigated by standard DB backups and replication, not by application code.
- **Not guaranteed side-effect idempotency for external APIs.** Slack, GitHub, and other external systems are called via their own APIs. Duplicate calls require idempotency keys at the connector level.
