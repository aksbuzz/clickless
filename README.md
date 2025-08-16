# ClickLess - Workflow Orchestration Engine

ClickLess is a resilient, event-driven workflow orchestration engine designed to automate complex business processes. It follows a distributed architecture with a clear separation of concerns between workflow state management (Orchestrator) and business logic execution (Workers).

## Table of Contents

1.  [Core Concepts](#core-concepts)
2.  [Architecture](#architecture)
3.  [Technology Stack](#technology-stack)
4.  [Developer Setup](#developer-setup)
5.  [Running the Application](#running-the-application)
6.  [Defining Workflows & Actions](#defining-workflows--actions)
7.  [Testing](#testing)
8.  [Observability](#observability)

## Core Concepts

*   **Workflow Definition**: A template for a business process, defined as a DAG (Directed Acyclic Graph) of steps. Stored in the database.

    ```
    {
        "description": "A simple invoice approval flow.",
        "start_at": "fetch_invoice",
        "steps": {
            "fetch_invoice": { "next": "validate_invoice" },
            "validate_invoice": { "next": "generate_report" },
            "generate_report": {
                "type": "delay",
                "duration_seconds": 15,
                "next": "archive_report" 
            },
            "archive_report": { 
            "next": "end",
            "retry": {
                "max_attempts": 3,
                "delay_seconds": 5
                }
            }
        }
    }
    ```

*   **Workflow Instance**: A running instance of a workflow definition. It maintains its own state (`data` blob), history, and current step.
*   **Action**: A single unit of work (e.g., call an API, query a database). The business logic for an action is defined by a **Primitive Handler** in code and a specific **Action Definition** in the database.
*   **Primitive Handler**: A generic, reusable piece of code that knows *how* to perform a type of task (e.g., make an HTTP request, upload to S3).
*   **Event-Driven**: The system progresses through state transitions by passing messages asynchronously between services.

## Architecture

ClickLess is comprised of several key components that work together over a message bus (RabbitMQ).

![alt text](docs/image.png)

#### 1. Orchestration Service
*   **Responsibility**: The brain of the system. It is the single source of truth for a workflow's state.
*   **Function**:
    *   Starts, stops, and resumes workflow instances.
    *   Receives `STEP_COMPLETE` or `STEP_FAILED` events from workers.
    *   Determines the next step in the workflow based on the definition.
    *   Schedules new tasks for workers by placing messages on the `actions_queue`.
    *   Handles system steps like delays, retries, and failures.
*   It is stateless and idempotent; all state is persisted in the PostgreSQL database.

#### 2. Worker Service
*   **Responsibility**: Executes the actual business logic for a workflow step.
*   **Function**:
    *   Listens for messages on the `actions_queue`.
    *   Upon receiving a task, it loads the required **Action Definition** from the database.
    *   It uses the appropriate **Primitive Handler** (e.g., `HttpRequestPrimitive`) to execute the task using the configuration from the database.
    *   Once execution is complete, it sends a `STEP_COMPLETE` or `STEP_FAILED` event back to the `orchestration_queue`.
*   The worker is **not allowed to modify the core workflow state directly**. It only executes its task and reports the outcome.

#### 3. PostgreSQL Database
*   **Responsibility**: The system's persistence layer.
*   **Key Tables**:
    *   `workflow_definitions`: Stores the templates for all workflows.
    *   `workflow_instances`: Tracks the state, data, and history of every running workflow.
    *   `action_definitions`: Stores the configuration for reusable business actions.
    *   `outbox`: Implements the Transactional Outbox pattern for reliable message dispatching.

#### 4. RabbitMQ (Message Bus)
*   **Responsibility**: Provides reliable, asynchronous communication between the Orchestrator and Workers.
*   **Key Queues**:
    *   `orchestration_queue`: For events directed to the Orchestrator (e.g., `STEP_COMPLETE`).
    *   `actions_queue`: For tasks directed to the Workers (e.g., `fetch_invoice`).
    *   Each queue is paired with a Dead-Letter Queue (DLQ) to isolate and handle "poison pill" messages.

#### 5. Message Relay
*   **Responsibility**: Ensures guaranteed message delivery from the database to RabbitMQ.
*   **Function**: A background process that polls the `outbox` table and publishes messages to RabbitMQ. This decouples the core application logic from message broker availability.

## Technology Stack

*   **Language**: Python 3.10+
*   **Framework**: Celery (for task queuing and workers)
*   **Database**: PostgreSQL
*   **Message Broker**: RabbitMQ
*   **Caching/Celery Backend**: Redis
*   **Containerization**: Docker & Docker Compose

## Developer Setup

#### Prerequisites
*   Docker and Docker Compose
*   Python 3.10+
*   `poetry`

#### 1. Clone the Repository
```bash
git clone <your-repo-url>
cd clickless
```

#### 2. Configure Environment Variables
Copy the example environment file and customize it for your local setup.
```bash
cp .env.example .env
```
Key variables in `.env`:
*   `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
*   `RABBITMQ_URL`
*   `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`

#### 3. Build and Start Services
This command will build the Docker images and start all the required services (Postgres, RabbitMQ, Redis, and the application services).
```bash
docker-compose up --build -d
```
The `-d` flag runs the containers in detached mode.

#### 4. Setup the Database
Run the database migrations to create the necessary tables.
```bash
# Execute this command in a new terminal
docker-compose exec orchestrator alembic upgrade head
```

## Running the Application

Once the setup is complete, the application services will be running inside Docker containers.

*   **Orchestrator Service**: Listens to `orchestration_queue`.
*   **Worker Service**: Listens to `actions_queue`.
*   **Message Relay**: Periodically scans the `outbox` table.
*   **API Service**: To interact with the application.

#### Interacting with the API (Example)
You can start a new workflow by sending a request to the API endpoint (assuming you have an API gateway service).

```bash
curl -X POST http://localhost:8000/workflows/{workflow_unique_name}/run \
     -H "Content-Type: application/json" \
     -d '{
       "data": { "invoice_id": "inv_12345" }
     }'
```

#### Viewing Logs
To see the logs from all services in real-time:
```bash
docker-compose logs -f
```
To view logs for a specific service:
```bash
docker-compose logs -f worker
```

## Defining Workflows & Actions

A key feature of ClickLess is defining business logic in the database.

1.  **Create a Primitive Handler (Code)**: If a new *type* of action is needed (e.g., interacting with SFTP), add a new `...Primitive` class in `src/worker/primitives.py`. This should be a rare event.
2.  **Define an Action (Database)**: To create a new action (e.g., "fetch-user-profile-from-api"), add a new row to the `action_definitions` table. This involves providing the `handler_type` (e.g., `http_request`) and the specific `config` JSON for that action. These definitions should be managed via Alembic migration scripts.
3.  **Define a Workflow (Database)**: Define the sequence of steps and their connections in the `workflow_definitions` table, referencing the action `name`s.

## Testing

The project is configured with `pytest`.

To run all tests:
```bash
pytest
```

## TODO

1. Add Monitoring & Observability
2. UI: Workflow Designer
3. Webhook Handler
4. Scheduler service to listen for workflows to process
5. Orchestration heartbeat for stuck worker processes