# Architecture Decision Records

This directory is the decision log for the workflow automation platform. Each ADR states the context, the decision, alternatives, and the consequences, including the known problems. **The log describes the code as it is** ([ADR 0001](0001-record-architecture-decisions.md)): an ADR is edited when its code changes, and deleted when the code is gone.

ADRs 0004 to 0016 were written after the fact from the code, the git history and the early design notes; their "alternatives considered" sections reflect evident trade-offs, not a record of past discussions. ADRs 0017 to 0021 were written as the decisions were taken.

References such as `F-24` point to findings in the review, [`../audit-2026-10-07.md`](../audit-2026-10-07.md), which lists what is fixed and what is still open.

| # | Decision | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0004](0004-workflows-as-versioned-json-definitions.md) | Workflows as versioned JSON documents | Accepted - under review |
| [0008](0008-connector-registry-and-trigger-handler-ports.md) | Connector registry and trigger handler ports | Accepted - under review |
| [0009](0009-webhook-trigger-ingestion-and-signature-verification.md) | Webhook ingestion and signature verification | Accepted - under review |
| [0011](0011-connection-credentials-stored-in-postgres.md) | Connection credentials stored in Postgres | Accepted - under review |
| [0012](0012-synchronous-psycopg2-with-per-process-pools.md) | Synchronous psycopg2 with small per-process pools | Accepted |
| [0013](0013-structured-logging-request-correlation-and-prometheus-metrics.md) | Structured logging, correlation, metrics and health | Accepted - under review |
| [0014](0014-schema-management-with-init-sql-and-manual-migrations.md) | Schema management with `init.sql` and numbered migrations | Accepted - under review |
| [0015](0015-module-layout-and-single-image-multiple-roles.md) | Module layout, one image for the API and the worker | Accepted - under review |
| [0016](0016-react-spa-served-by-nginx-with-polling.md) | React SPA served by nginx, polling for status | Accepted - under review |
| [0017](0017-postgres-backed-job-queue-replaces-outbox-broker-and-celery.md) | A PostgreSQL job queue replaces the outbox, RabbitMQ, Celery and Redis | Accepted |
| [0018](0018-one-job-per-step-with-lease-fencing-and-single-transaction-advance.md) | One job per step, lease fencing, single-transaction advance | Accepted |
| [0019](0019-remove-the-in-process-python-code-step.md) | Remove the in-process Python code step | Accepted |
| [0020](0020-shared-api-key-authentication-and-private-internal-services.md) | Shared API key authentication, private internal services | Accepted |
| [0021](0021-guard-outbound-requests-from-workflow-handlers.md) | Guard outbound requests from workflow handlers | Accepted |

**Numbers that no longer exist** (their decisions were replaced and their code removed; the reasoning that still matters is in 0017 and 0018, and git history has the originals): 0002 transactional outbox with a polling relay, 0003 Celery on RabbitMQ with late acknowledgement and dead-letter queues, 0005 event-driven orchestrator with a per-instance Redis lock, 0006 at-least-once execution with a worker-side idempotency check, 0007 recovery sweeper, 0010 in-process Python code step (removed by 0019).

## Conventions

- File name: `NNNN-kebab-title.md`. Numbers are never reused or reordered.
- Statuses: `Proposed`, `Accepted`, `Accepted - under review`, `Rejected`.
- Edit an ADR when the code it describes changes; delete it when that code is gone and say so in the list above.
- A PR that changes one of these decisions edits or adds an ADR.

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
