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
- **Visual builder** - Easy drag and drop interface

---

## How to Install

### What you need:

- **Docker** and **Docker Compose**
- **Python 3.12** or newer
- **Poetry** (Python package manager)

### Step 1: Download the code

```bash
git clone <your-repo-url>
cd workflow_automate
```

### Step 2: Setup environment

Generate your settings. This creates `.env` with random passwords and an API key, and prints the key:

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
| `GITHUB_WEBHOOK_SECRET`, `SLACK_SIGNING_SECRET`, `TRELLO_API_SECRET` + `TRELLO_CALLBACK_URL` | Secrets used to verify webhooks from each provider. A provider's webhook is **rejected while its secret is empty**. Point providers at `http://<your-host>:8000/triggers/<github\|slack\|trello>/webhook`. |
| `OUTBOUND_ALLOW_HOSTS` | Workflows may only call public addresses. List internal hosts (comma-separated) that they may also call, for example a private database. |

RabbitMQ, Redis and PostgreSQL are not published to the host. For a local database browser run `docker compose --profile dev-tools up` (adminer on http://127.0.0.1:8080).

### Create a workflow

1. Go to http://localhost:3000
2. Click "**New Workflow**"
3. Add steps (actions)
4. Connect the steps
5. Save your workflow
6. Click "**Run**" to start it

---

## What's Inside?

| Part | What it does |
|------|--------------|
| **Frontend** | Website you see and click |
| **API** | Receives your requests |
| **Engine** | Controls the workflows |
| **Worker** | Does the actual tasks |
| **Database** | Saves all data |
| **Message Queue** | Sends messages between parts |

---

## Common Tasks

### See logs (what is happening)

See all logs:
```bash
docker-compose logs -f
```

See logs for one part only:
```bash
docker-compose logs -f worker
```

### Stop the app

```bash
docker-compose down
```

### Stop and delete everything

```bash
docker-compose down -v
```

**Warning**: This deletes your database!

### Restart the app

```bash
docker-compose restart
```

---

## Technology Used

- **Python** - Programming language
- **FastAPI** - Web framework
- **PostgreSQL** - Database
- **RabbitMQ** - Message system
- **Redis** - Fast cache
- **React** - Website framework
- **Docker** - Container system
- **Celery** - Task queue

---

## Project Structure

```
workflow_automate/
├── frontend/          # Website code (React)
├── src/
│   ├── api/          # API endpoints
│   ├── engine/       # Workflow controller
│   ├── worker/       # Task executor
│   ├── relay/        # Message sender
│   └── shared/       # Common code
├── infrastructure/    # Database setup
├── docker-compose.yml # Docker configuration
└── .env              # Your settings
```

---

## Examples

### Example: Simple Workflow

```json
{
  "description": "Send a welcome email",
  "start_at": "send_email",
  "steps": {
    "send_email": {
      "type": "action",
      "connector_id": "http",
      "action_id": "post_request",
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

Backend unit tests (Python 3.12, dependencies from `poetry.lock`):

```bash
poetry install --no-root
make test        # or: python -m pytest -q tests
```

Frontend lint and build:

```bash
cd frontend && npm ci && npm run lint && npm run build
```

End-to-end smoke test. It runs the seeded workflow down both branches against a running stack:

```bash
cp .env.example .env
docker compose up --build -d
make smoke       # or: sh scripts/smoke.sh
```

CI (`.github/workflows/ci.yml`) runs all three.

### Add a new connector

1. Go to `src/shared/connectors/definitions/`
2. Create a new file (example: `myapp.py`)
3. Define your connector
4. Register it

### Database changes

Edit this file:
```
infrastructure/postgres/init.sql
```

Then restart:
```bash
docker-compose down -v
docker-compose up --build -d
```

---

## Future Plans

- [ ] Add more connectors
- [ ] UX improvements

---

## License

MIT License - You can use this freely.
