# Workflow Automation App

A tool to automate your business tasks. This app helps you create **workflows**. A workflow is a list of tasks that run automatically.

**Example:**
- Receive an order → Classify priority → Set shipping days → Log the result

---

## Main Features

- **Create workflows** - Build step-by-step tasks
- **Connect apps** - Link with GitHub, Slack, databases
- **Run automatically** - Start workflows with events
- **See progress** - Track what is happening
- **Visual builder** - A step-by-step form wizard with a live graph preview

---

## How to Install

### What you need:

- **Docker** and **Docker Compose** (that is all you need to run the app)
- To run the tests or work on the code: **Python 3.12**, **Poetry**, and **Node 22.18** or newer for the frontend

### Step 1: Download the code

```bash
git clone <your-repo-url>
cd workflow_automate
```

### Step 2: Setup environment

Generate your settings. This creates `.env` with random passwords, an API key and an encryption key, and prints the API key:

```bash
sh scripts/init-env.sh
```

Do not copy `.env.example` by hand: Docker Compose and the API refuse to start without these secrets.

### Step 3: Start the app

Run this command:

```bash
docker compose up --build -d
```

Wait 1-2 minutes. Docker will download and start everything.

---

## How to Use

### Open the app

After starting, open your web browser:

- **Frontend (Website)**: http://localhost:3000. It asks for the API key printed in step 2 (also in `.env` as `API_KEY`).
- **API (Backend)**: http://localhost:8000. Every request needs the header `Authorization: Bearer <API_KEY>`.

Both listen on this machine only. Set `BIND_ADDRESS=0.0.0.0` in `.env` to expose them, and only do that behind something that provides TLS and access control.

### Security settings

| Setting (in `.env`) | What it does |
|---|---|
| `API_KEY` | The shared key for the API and UI. At least 16 characters; the API will not start without it. |
| `SECRETS_KEY` | Encrypts the credentials stored in connections (GitHub tokens, Slack webhook URLs and so on). A Fernet key; the API and the worker will not start without one. **Keep a copy of `.env`**: without this key stored credentials cannot be read and must be entered again. |
| `GITHUB_WEBHOOK_SECRET`, `SLACK_SIGNING_SECRET`, `TRELLO_API_SECRET` + `TRELLO_CALLBACK_URL` | Secrets used to verify webhooks from each provider. A provider's webhook is **rejected while its secret is empty**. Point providers at `http://<your-host>:8000/triggers/<github\|slack\|trello>/webhook`. |
| `OUTBOUND_ALLOW_HOSTS` | Workflows may only call public addresses. List internal hosts (comma-separated) that they may also call, for example a private database. |

Credentials saved in a connection are write-only: the UI and API never show them again (the form shows "saved" and keeps the value when left blank), and they are stored encrypted. To change `SECRETS_KEY` put the new key first, keep the old one after a comma (`SECRETS_KEY=new,old`), restart and run `docker compose run --rm api python -m src.api.encrypt_connections`; then the old key can be removed. Credentials typed directly into a step instead of a connection are not protected, so use connections. See [ADR 0011](docs/adr/0011-connection-credentials-stored-in-postgres.md).

PostgreSQL is not published to the host. For a local database browser run `docker compose --profile dev-tools up` (adminer on http://127.0.0.1:8080).

### Create a workflow

1. Go to http://localhost:3000
2. Click "**New Workflow**"
3. Add steps (actions)
4. Connect the steps
5. Save your workflow
6. Click "**Run**" to start it

---

## What's Inside?

Four containers:

| Part | What it does |
|------|--------------|
| **frontend** | The website (React, served by nginx). It also proxies `/api` to the API. |
| **api** | Receives requests and webhooks, stores workflows, starts and cancels runs. |
| **worker** | Runs the steps. It takes jobs from the database, one step per job, and can run many at once. |
| **postgres** | Everything else: workflows, run state, history, and the job queue itself. |

There is no message broker, cache or separate scheduler. See [docs/architecture.md](docs/architecture.md).

---

## Common Tasks

### See logs (what is happening)

See all logs:
```bash
docker compose logs -f
```

See logs for one part only:
```bash
docker compose logs -f worker
```

### Stop the app

```bash
docker compose down
```

### Stop and delete everything

```bash
docker compose down -v
```

**Warning**: This deletes your database!

### Restart the app

```bash
docker compose restart
```

### How long history is kept

Finished runs (completed, failed or cancelled) and their step history are deleted after `RETENTION_DAYS` days, **30 by default**. Set it in `.env`; `0` keeps everything forever. Runs that have not finished are never deleted, and deleted history can only be recovered from a database backup. The worker does this in the background (first pass a minute after it starts, then hourly). See [ADR 0022](docs/adr/0022-delete-finished-runs-after-a-retention-period.md).

### Run more workers

Each worker runs up to `WORKER_CONCURRENCY` steps at once (default 8). For more capacity, raise that or add workers:

```bash
docker compose up -d --scale worker=3
```

### Check on it

- `GET /health` (needs the API key) reports PostgreSQL and the job queue. It goes unhealthy when due jobs are not being picked up, which means no worker is running.
- `GET /ready` (public) is the container readiness probe.
- Metrics: `GET /metrics` on the API, and the worker serves its own on port 9100 inside the compose network (workflow and step counts, durations, retries, failures).
- Jobs that could not be run (a step that kept killing its worker) stay in the `jobs` table with status `dead`:
  ```sql
  SELECT id, instance_id, step_name, last_error FROM jobs WHERE status = 'dead';
  ```

---

## Technology Used

- **Python** - Programming language
- **FastAPI** - Web framework
- **PostgreSQL** - Database and job queue
- **React** and **TypeScript** - Website
- **nginx** - Serves the website and proxies the API
- **Docker** - Container system

---

## Project Structure

```
workflow_automate/
├── frontend/             # Website code (React)
├── src/
│   ├── api/              # HTTP API, webhook ingestion, authentication
│   ├── engine/           # Job queue and workflow state machine, worker threads
│   ├── worker/           # Worker process entry point and the connector handlers
│   └── shared/           # Database access, connector catalogue, outbound guard, logging, metrics
├── infrastructure/
│   └── postgres/         # init.sql (schema and seed) and migrations for existing databases
├── tests/
│   ├── unit/             # No database needed
│   └── integration/      # Run against a real PostgreSQL
├── benchmarks/           # Throughput benchmarks for the worker and the API
├── scripts/              # init-env.sh (secrets) and smoke.sh (end-to-end check)
├── docs/                 # Architecture, reliability, scalability, decision records
├── docker-compose.yml    # The four services
└── .env                  # Your settings (created by scripts/init-env.sh)
```

---

## Examples

A definition is checked when you save it. Every problem is listed at once, for example a `next` that names no step, an unknown action or operator, a step without an action, or a loop made only of branch and delay steps; nothing is stored until the list is empty. Use `"next": "end"` on the last step. See [ADR 0023](docs/adr/0023-validate-workflow-definitions-when-they-are-saved.md).

### Example: Simple Workflow

```json
{
  "description": "Tell another system about a new order",
  "trigger": { "connector_id": "http", "trigger_id": "http_request_received", "config": {} },
  "start_at": "notify",
  "steps": {
    "notify": {
      "type": "action",
      "connector_id": "http",
      "action_id": "http_request",
      "config": {
        "url": "https://example.com/hooks/orders",
        "method": "POST",
        "body": { "order_id": "{{order.id}}" }
      },
      "next": "end"
    }
  }
}
```

### Example: Workflow with Branch

```json
{
  "description": "Classify order priority by quantity and set shipping days.",
  "trigger": { "connector_id": "http", "trigger_id": "http_request_received", "config": {} },
  "start_at": "check_quantity",
  "steps": {
    "check_quantity": {
      "type": "branch",
      "condition": { "field": "order.quantity", "operator": "gte", "value": 100 },
      "on_true": "set_expedited",
      "on_false": "set_standard"
    },
    "set_expedited": {
      "type": "action",
      "connector_id": "internal",
      "action_id": "transform_data",
      "config": { "set": { "priority": "high", "expedited": true, "shipping_days": 1 } },
      "next": "log_result"
    },
    "set_standard": {
      "type": "action",
      "connector_id": "internal",
      "action_id": "transform_data",
      "config": { "set": { "priority": "normal", "expedited": false, "shipping_days": 5 } },
      "next": "log_result"
    },
    "log_result": {
      "type": "action",
      "connector_id": "internal",
      "action_id": "log",
      "config": { "message": "Order processed: priority={{priority}}, shipping_days={{shipping_days}}" },
      "next": "end"
    }
  }
}
```

### Run tests

Backend tests (Python 3.12, dependencies from `poetry.lock`). The integration tests need a PostgreSQL where they may create databases; without `TEST_DATABASE_URL` they are skipped (and fail in CI):

```bash
poetry install --no-root
docker run -d --name pg -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust postgres:17-alpine
export TEST_DATABASE_URL=postgresql://postgres@localhost:5432/postgres
make test        # or: python -m pytest -q tests
```

Frontend lint, tests and build:

```bash
cd frontend && npm ci && npm run lint && npm test && npm run build
```

End-to-end smoke test. It runs the seeded workflow down both branches against a running stack and checks the security setup:

```bash
sh scripts/init-env.sh
docker compose up --build -d
make smoke       # or: sh scripts/smoke.sh
```

CI (`.github/workflows/ci.yml`) runs all three.

### Add a new connector

1. Describe it in `src/shared/connectors/definitions/myapp.py` (triggers, actions and their config fields, which the UI uses to build forms) and import it in `definitions/__init__.py`. Mark every credential field in its `connection_schema` with `"writeOnly": True` so it is encrypted and never returned; `tests/unit/test_connection_schemas.py` lists them and fails for a connector that is not covered.
2. Implement each action in `src/worker/handlers/myapp.py` with the `@action("action_id")` decorator and import the module in `src/worker/registry.py`. A handler receives its config with `{{templates}}` already resolved by the engine; it must not resolve them again. A handler that takes SQL or a connection string lists those keys in `untemplated_keys` so they are never built from data.
3. Anything that connects out on a user's behalf (URLs, hosts) must go through `src/shared/net_guard.py`.
4. A webhook trigger also needs a handler in `src/api/trigger_handlers/` that verifies the provider's signature.

### Database changes

`infrastructure/postgres/init.sql` creates the schema when the database is first created. To change the schema of an existing database, add a numbered SQL file to `infrastructure/postgres/migrations/` (and make `init.sql` produce the same result; `tests/integration/test_migration_job_queue.py` shows how to test that). Apply a migration with:

```bash
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < infrastructure/postgres/migrations/002_job_queue.sql
```

Upgrading from the version that used RabbitMQ, Redis and Celery: stop the stack, apply migration `002_job_queue.sql` (it turns unfinished instances into jobs so they resume), then start the new stack. Remove the old `RABBITMQ_*` and `REDIS_*` settings from `.env`.

Upgrading to a version with retention: apply migration `003_retention_index.sql` (same command as above), and decide `RETENTION_DAYS` first. About a minute after the first worker starts, every finished run older than the period (30 days unless you set it) is deleted.

Upgrading to encrypted connection credentials: run `sh scripts/init-env.sh --upgrade` to add `SECRETS_KEY` to your existing `.env` (keep a copy), restart the stack, then run `docker compose run --rm api python -m src.api.encrypt_connections` to encrypt the credentials already stored. Until you do, they still work as plaintext and are encrypted the next time each connection is saved.

---

## Documentation

- [docs/architecture.md](docs/architecture.md): how a workflow runs, end to end
- [docs/reliability.md](docs/reliability.md): what is guaranteed and how failures are handled
- [docs/scalability.md](docs/scalability.md): measured throughput, sizing for small servers, tuning
- [docs/worker-and-scheduler.md](docs/worker-and-scheduler.md): how workers pick up, delay and retry steps
- [docs/adr/](docs/adr/README.md): decision records
- [docs/audit-2026-10-07.md](docs/audit-2026-10-07.md): review findings and what is still open

---

## License

MIT License - You can use this freely.
