# Workflow Automation App

A tool to automate your business tasks.

---

## What is this?

This app helps you create **workflows**. A workflow is a list of tasks that run automatically.

**Example:**
- Get an invoice → Check if it's correct → Create a report → Save the report

---

## Main Features

✅ **Create workflows** - Build step-by-step tasks
✅ **Connect apps** - Link with GitHub, Slack, databases
✅ **Run automatically** - Start workflows with events
✅ **See progress** - Track what is happening
✅ **Visual builder** - Easy drag and drop interface

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

Copy the example file:

```bash
cp .env.example .env
```

Open `.env` file and add your settings.

### Step 3: Start the app

Run this command:

```bash
docker-compose up --build -d
```

Wait 1-2 minutes. Docker will download and start everything.

---

## How to Use

### Open the app

After starting, open your web browser:

- **Frontend (Website)**: http://localhost:3000
- **API (Backend)**: http://localhost:8000

### Create a workflow

1. Go to http://localhost:3000
2. Click "**New Workflow**"
3. Add steps (actions)
4. Connect the steps
5. Save your workflow
6. Click "**Run**" to start it

---

## What's Inside?

The app has these parts:

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

⚠️ **Warning**: This deletes your database!

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
  "description": "Check invoice amount",
  "start_at": "check_amount",
  "steps": {
    "check_amount": {
      "type": "branch",
      "condition": {
        "field": "amount",
        "operator": "gt",
        "value": 1000
      },
      "on_true": "approve",
      "on_false": "reject"
    },
    "approve": {
      "type": "action",
      "next": "end"
    },
    "reject": {
      "type": "action",
      "next": "end"
    }
  }
}
```


### Run tests

```bash
pytest
```

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

## Important Notes

📌 Always use the **.env** file for passwords and secrets
📌 Don't share your **.env** file
📌 Check **logs** if something goes wrong
📌 The frontend is at **port 3000**
📌 The API is at **port 8000**

---

## Future Plans

- [ ] Add more connectors
- [ ] UX improvements

---

## License

MIT License - You can use this freely.
