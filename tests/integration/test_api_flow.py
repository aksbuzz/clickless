"""The HTTP API on top of the real engine: start, trigger, cancel, resume, inspect, health."""
import hashlib
import hmac
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.worker.registry import get_registry
from tests.integration.helpers import Record, action, executions, instance, running_worker, terminal, wait_until

KEY = "k" * 32
AUTH = {"Authorization": f"Bearer {KEY}"}


@pytest.fixture
def client(monkeypatch, conn):
    monkeypatch.setenv("API_KEY", KEY)
    monkeypatch.delenv("HEALTH_MAX_JOB_AGE_SECONDS", raising=False)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def handlers():
    return get_registry()


def create_workflow(client, definition) -> str:
    name = f"api_{uuid.uuid4().hex[:8]}"
    response = client.post("/workflows", json={"name": name, "definition": definition}, headers=AUTH)
    assert response.status_code == 201, response.text
    return name


def log_step(nxt="end"):
    return {"type": "action", "connector_id": "internal", "action_id": "log", "config": {"message": "hi"}, "next": nxt}


def test_a_workflow_started_over_http_runs_to_completion(client, conn, handlers):
    response = client.post("/workflows/order_priority_workflow/run", json={"data": {"order": {"quantity": 150}}}, headers=AUTH)
    assert response.status_code == 200
    iid = response.json()["instance_id"]

    with running_worker(handlers):
        wait_until(terminal(conn, iid))

    shown = client.get(f"/instances/{iid}", headers=AUTH).json()
    assert shown["status"] == "completed" and shown["data"]["priority"] == "high"
    steps = client.get(f"/instances/{iid}/steps", headers=AUTH).json()
    assert [s["step_name"] for s in steps] == ["check_quantity", "set_expedited", "log_result"]
    assert all("input_data" not in s for s in steps)


def test_a_failed_step_shows_its_error_to_the_api_user(client, conn, handlers):
    handlers["boom"] = Record(fail_times=99)
    name = create_workflow(client, {"trigger": {"connector_id": "http", "trigger_id": "http_request_received", "config": {}},
                                    "start_at": "a", "steps": {"a": {"type": "action", "connector_id": "internal", "action_id": "log",
                                                                     "config": {}, "next": "end"}}})
    # run it with a handler that fails: swap the real `log` handler for one that always fails
    handlers["log"] = handlers["boom"]
    iid = client.post(f"/workflows/{name}/run", json={"data": {}}, headers=AUTH).json()["instance_id"]
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    assert client.get(f"/instances/{iid}", headers=AUTH).json()["status"] == "failed"
    steps = client.get(f"/instances/{iid}/steps", headers=AUTH).json()
    assert steps[0]["status"] == "failed" and steps[0]["error_details"] == "boom 1"


def test_a_webhook_trigger_starts_an_instance(client, conn, handlers):
    name = create_workflow(client, {"trigger": {"connector_id": "http", "trigger_id": "http_request_received", "config": {}},
                                    "start_at": "a", "steps": {"a": log_step()}})
    response = client.post(f"/webhooks/{name}", json={"data": {"x": 1}}, headers=AUTH)
    assert response.status_code == 200
    iid = response.json()["instance_id"]
    with running_worker(handlers):
        wait_until(terminal(conn, iid))
    assert instance(conn, iid)["data"] == {"x": 1}


def test_a_signed_github_delivery_starts_the_matching_workflows(client, conn, handlers, monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cret")
    matching = create_workflow(client, {"trigger": {"connector_id": "github", "trigger_id": "github_issue_opened",
                                                    "config": {"repository": "acme/widgets"}},
                                        "start_at": "a", "steps": {"a": log_step()}})
    create_workflow(client, {"trigger": {"connector_id": "github", "trigger_id": "github_issue_opened",
                                         "config": {"repository": "acme/other"}},
                             "start_at": "a", "steps": {"a": log_step()}})
    payload = json.dumps({
        "action": "opened",
        "repository": {"full_name": "acme/widgets", "name": "widgets", "owner": {"login": "acme"}},
        "issue": {"number": 7, "title": "Crash", "body": "", "html_url": "u", "user": {"login": "bob"}, "labels": []},
        "sender": {"login": "bob"},
    }).encode()
    signature = "sha256=" + hmac.new(b"s3cret", payload, hashlib.sha256).hexdigest()

    response = client.post("/triggers/github/webhook", content=payload,
                           headers={"x-github-event": "issues", "x-hub-signature-256": signature})

    assert response.status_code == 200
    started = response.json()["triggered"]
    assert [t["workflow_name"] for t in started] == [matching]
    with running_worker(handlers):
        wait_until(terminal(conn, started[0]["instance_id"]))
    assert instance(conn, started[0]["instance_id"])["data"]["issue"]["number"] == 7


def test_cancelling_over_http(client, conn):
    name = create_workflow(client, {"trigger": {"connector_id": "http", "trigger_id": "http_request_received", "config": {}},
                                    "start_at": "a", "steps": {"a": log_step()}})
    iid = client.post(f"/workflows/{name}/run", json={"data": {}}, headers=AUTH).json()["instance_id"]
    assert client.post(f"/instances/{iid}/cancel", headers=AUTH).status_code == 200
    assert instance(conn, iid)["status"] == "cancelled"
    assert client.post(f"/instances/{iid}/cancel", headers=AUTH).status_code == 409
    assert client.post(f"/instances/{uuid.uuid4()}/cancel", headers=AUTH).status_code == 404


def test_resuming_a_waiting_instance_over_http(client, conn, handlers):
    name = create_workflow(client, {"trigger": {"connector_id": "http", "trigger_id": "http_request_received", "config": {}},
                                    "start_at": "w", "steps": {"w": {"type": "wait_for_event", "next": "a"}, "a": log_step()}})
    iid = client.post(f"/workflows/{name}/run", json={"data": {}}, headers=AUTH).json()["instance_id"]
    assert client.post(f"/instances/{iid}/events", json={"data": {}}, headers=AUTH).status_code == 409   # not waiting yet
    with running_worker(handlers):
        wait_until(lambda: [e for e in executions(conn, iid) if e["status"] == "running"])
        response = client.post(f"/instances/{iid}/events", json={"data": {"approved": True}}, headers=AUTH)
        assert response.status_code == 200 and response.json()["step"] == "w"
        wait_until(terminal(conn, iid))
    assert instance(conn, iid)["data"]["approved"] is True


def test_starting_an_unknown_workflow_is_a_404(client):
    assert client.post("/workflows/no_such_workflow/run", json={"data": {}}, headers=AUTH).status_code == 404


def test_health_is_green_while_a_worker_is_taking_jobs(client, conn, handlers):
    with running_worker(handlers):
        response = client.get("/health", headers=AUTH)
    assert response.status_code == 200
    assert set(response.json()["checks"]) == {"postgres", "queue"}


def test_health_goes_red_when_due_jobs_are_not_being_picked_up(client, conn, monkeypatch):
    monkeypatch.setenv("HEALTH_MAX_JOB_AGE_SECONDS", "5")
    name = create_workflow(client, {"trigger": {"connector_id": "http", "trigger_id": "http_request_received", "config": {}},
                                    "start_at": "a", "steps": {"a": log_step()}})
    iid = client.post(f"/workflows/{name}/run", json={"data": {}}, headers=AUTH).json()["instance_id"]
    conn.cursor().execute("UPDATE jobs SET run_at = now() - interval '2 minutes' WHERE instance_id = %s", (iid,))
    response = client.get("/health", headers=AUTH)          # no worker is running
    assert response.status_code == 503
    assert response.json()["detail"]["checks"]["queue"]["status"] == "unhealthy"


def test_the_readiness_probe_needs_no_key(client):
    assert client.get("/ready").status_code == 200
