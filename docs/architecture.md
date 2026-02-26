# System Architecture

## Overview

This is a distributed workflow automation platform. Users define workflows as a DAG of steps; the system executes them reliably in response to external triggers (webhooks, manual API calls) or on a schedule.

**Technology stack:**

| Component | Technology |
|---|---|
| API server | FastAPI (Python) |
| Message broker | RabbitMQ |
| Task queue | Celery |
| Database | PostgreSQL |
| Distributed locks | Redis |
| Frontend | React (TypeScript) |

---

## High-Level Architecture

```
External Systems (GitHub, Slack, etc.)
         │
         ▼
 ┌──────────────┐
 │  FastAPI     │  ← REST API + webhook ingestion
 │  API Server  │
 └──────┬───────┘
        │  writes atomically
        ▼
 ┌──────────────┐
 │  PostgreSQL  │  ← workflow_instances + outbox table
 └──────┬───────┘
        │  relay polls
        ▼
 ┌──────────────┐
 │ Relay Service│  ← moves outbox rows → RabbitMQ
 └──────┬───────┘
        │
        ▼
 ┌──────────────┐
 │   RabbitMQ   │  ← orchestration_queue / actions_queue
 └──┬───────────┘
    │
    ├──► Engine Worker  (orchestration logic, state machine)
    │
    └──► Action Workers (execute connectors: GitHub, Slack, HTTP…)
```

---

## Core Concepts

### Workflow Definition

A workflow is a versioned JSON document stored in `workflow_versions.definition`:

```json
{
  "trigger": {
    "connector_id": "github",
    "trigger_id": "github_issue_opened",
    "config": {}
  },
  "start_at": "notify_slack",
  "steps": {
    "notify_slack": {
      "connector_id": "slack",
      "action_id": "slack_send_message",
      "config": { "text": "New issue: {{issue.title}}" },
      "connection_id": "<connection-uuid>",
      "retry": { "max_attempts": 3, "delay_seconds": 5 },
      "next": "end"
    }
  }
}
```

Each step can be:
- **action** – delegates to a connector handler (Slack, GitHub, HTTP, etc.)
- **branch** – conditional routing based on instance data
- **delay** – pauses execution for N seconds
- **wait_for_event** – suspends until an external event arrives

### Workflow Instance

Each execution of a workflow is a `workflow_instance` row:

```
status: pending → running → completed
                          → failed
                          → cancelled
```

`instance.data` is a mutable JSONB blob that accumulates outputs from each step, available as template variables (e.g. `{{github_issue.number}}`).

---

## Execution Flow

### 1. Trigger Ingestion

```
POST /triggers/{connector_id}/webhook
```

1. Validate signature (HMAC for GitHub, signing secret for Slack).
2. Parse raw webhook body into a normalized `TriggerEvent`.
3. Query DB for all workflows whose trigger matches `(connector_id, trigger_id)`.
4. For each matching workflow, in a **single DB transaction**:
   - `INSERT workflow_instances` (status = `pending`, data = trigger payload)
   - `INSERT outbox` (destination = `orchestration_queue`, payload = `START_WORKFLOW` event)

Transactional coupling is the core reliability guarantee — the instance and the outbox message are either both saved or neither is.

### 2. Relay (Outbox → RabbitMQ)

The **Relay Service** runs continuously as a separate process:

```python
SELECT id, destination, payload
FROM outbox
WHERE processed_at IS NULL
  AND publish_at <= NOW()
LIMIT 100
FOR UPDATE SKIP LOCKED
```

For each row it:
1. Sends the message to the correct Celery task (`engine.orchestrate` or `worker.execute_action`).
2. Sets `processed_at = NOW()` in the same transaction.

`FOR UPDATE SKIP LOCKED` means multiple relay replicas can run safely in parallel — each row is claimed by exactly one relay instance.

### 3. Orchestration Engine

The engine worker consumes from `orchestration_queue` and runs a state machine:

```
Event: START_WORKFLOW
  └─► _handle_workflow_start()
        load instance → verify pending
        transition to start_at step

Event: STEP_COMPLETE
  └─► _handle_step_completion()
        verify step matches current step (stale-event guard)
        mark step_execution COMPLETED
        merge output_data into instance.data
        transition to next step

Event: STEP_FAILED
  └─► _handle_step_failure()
        attempts < max_attempts?
          yes → schedule retry with delay
          no  → mark instance FAILED
```

**Transition logic** (`_transition_to_step`):

| Step type | Action |
|---|---|
| `"end"` | Mark instance COMPLETED |
| `delay` | Schedule `STEP_COMPLETE` event at `now + duration_seconds` |
| `branch` | Evaluate condition, recurse into `on_true` / `on_false` |
| `wait_for_event` | Suspend; optional timeout via scheduled `STEP_FAILED` |
| action | Create `workflow_step_executions` row; enqueue to `actions_queue` |

A **Redis lock** keyed on the instance ID serializes all events for the same instance, preventing race conditions when two events arrive simultaneously.

### 4. Action Workers

Action workers consume from `actions_queue`:

1. **Idempotency check** — if the step is already `COMPLETED` in `workflow_step_executions`, skip and do nothing.
2. Resolve connection credentials from `connections` table and merge into step config.
3. Look up handler in the registry by `(connector_id, action_id)`.
4. Call `handler.execute(instance_id, instance_data, config)`.
5. Write result back to the outbox as `STEP_COMPLETE` or `STEP_FAILED`.

Multiple worker replicas run in parallel (default 2), providing horizontal throughput.

---

## Key Database Tables

| Table | Purpose |
|---|---|
| `workflows` | Workflow identity (name, id) |
| `workflow_versions` | Versioned definitions (JSONB) |
| `workflow_instances` | Running/completed execution state |
| `workflow_step_executions` | Per-step audit log + idempotency |
| `outbox` | Transactional message relay buffer |
| `connections` | Stored connector credentials |

---

## Services at a Glance

| Service | Entry Point | Role |
|---|---|---|
| `api` | `src/api/main.py` | HTTP server, trigger ingestion |
| `engine` | `src/orchestration/entrypoint/celery_task.py` | Orchestration state machine |
| `worker` | `src/worker/task.py` | Action execution |
| `relay` | `src/relay/entrypoint/main.py` | Outbox → RabbitMQ relay |
| `beat` | Celery Beat | Periodic tasks (recovery sweeper) |
