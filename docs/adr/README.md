# Architecture Decision Records

This directory is the decision log for the workflow automation platform. Each ADR states the context, the decision, alternatives, and the consequences, including the known problems.

ADRs 0002 to 0016 were written retrospectively on 2026-10-07 from the code, the git history and `docs/*.md`. They describe the system as it is today. ADRs 0017 and 0018 (2026-10-10) are forward-looking proposals backed by a working spike in [`../../spikes/pg-queue/`](../../spikes/pg-queue/README.md); the ADRs they would supersede stay `Accepted` until the proposals are accepted. Their "alternatives considered" sections reflect evident trade-offs, not a record of past discussions; confirm with the original authors when it matters. References such as `F-07` point to findings in [`../audit-2026-10-07.md`](../audit-2026-10-07.md).

| # | Decision | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-transactional-outbox-with-polling-relay.md) | Transactional outbox with a polling relay | Accepted - under review |
| [0003](0003-celery-on-rabbitmq-with-separate-queues-and-late-ack.md) | Celery on RabbitMQ, separate queues, late ack | Accepted - under review |
| [0004](0004-workflows-as-versioned-json-definitions.md) | Workflows as versioned JSON documents | Accepted - under review |
| [0005](0005-event-driven-orchestrator-with-per-instance-redis-lock.md) | Event-driven orchestrator with per-instance Redis lock | Accepted - under review |
| [0006](0006-at-least-once-execution-and-step-level-idempotency.md) | At-least-once execution, step-level idempotency | Accepted - under review |
| [0007](0007-stuck-instance-recovery-sweeper.md) | Stuck-instance recovery sweeper | Accepted - under review (not running) |
| [0008](0008-connector-registry-and-trigger-handler-ports.md) | Connector registry and trigger handler ports | Accepted - under review |
| [0009](0009-webhook-trigger-ingestion-and-signature-verification.md) | Webhook ingestion and signature verification | Accepted - under review |
| [0010](0010-in-process-python-code-step.md) | In-process Python code step | Accepted - under review (security) |
| [0011](0011-connection-credentials-stored-in-postgres.md) | Connection credentials stored in Postgres | Accepted - under review |
| [0012](0012-synchronous-psycopg2-with-per-process-pools.md) | Synchronous psycopg2 with per-process pools | Accepted - under review |
| [0013](0013-structured-logging-request-correlation-and-prometheus-metrics.md) | Structured logging, correlation, Prometheus metrics | Accepted - under review |
| [0014](0014-schema-management-with-init-sql-and-manual-migrations.md) | Schema management with `init.sql` and manual migrations | Accepted - under review (process gap) |
| [0015](0015-module-layout-and-single-image-multiple-roles.md) | Module layout, single image for all roles | Accepted - under review |
| [0016](0016-react-spa-served-by-nginx-with-polling.md) | React SPA served by nginx, polling for status | Accepted - under review |
| [0017](0017-postgres-backed-job-queue-replaces-outbox-broker-and-celery.md) | Postgres-backed job queue replaces outbox, broker, Celery, Redis lock | **Proposed** |
| [0018](0018-one-job-per-step-with-lease-fencing-and-single-transaction-advance.md) | One job per step, lease fencing, single-transaction advance | **Proposed** |

## Conventions

- File name: `NNNN-kebab-title.md`. Numbers are never reused or reordered.
- Statuses: `Proposed`, `Accepted`, `Accepted - under review`, `Superseded by NNNN`, `Rejected`.
- To change a decision, add a new ADR and mark the old one superseded. Corrections of fact and added cross-references are fine in place.
- A PR that changes one of these decisions adds or supersedes an ADR.

## Template

```markdown
# NNNN. Title

- Status: Proposed
- Date: YYYY-MM-DD

## Context
What forces are at play? What problem needs a decision?

## Decision
What we will do, stated in full sentences.

## Alternatives considered
Options that were weighed, and why they were not chosen.

## Consequences
Positive, negative, and what becomes easier or harder.

## References
Code, docs, tickets, other ADRs.
```
