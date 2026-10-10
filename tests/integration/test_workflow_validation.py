"""Both save paths (new workflow, new version) refuse a bad definition and say everything that is wrong with it."""
import copy
import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

KEY = "k" * 32
AUTH = {"Authorization": f"Bearer {KEY}"}

GOOD = {
    "trigger": {"connector_id": "http", "trigger_id": "http_request_received", "config": {}},
    "start_at": "check",
    "steps": {
        "check": {"type": "branch", "condition": {"field": "n", "operator": "gt", "value": 1}, "on_true": "log", "on_false": "end"},
        "log": {"type": "action", "connector_id": "internal", "action_id": "log", "config": {"message": "hi"}, "next": "end"},
    },
}

BAD = {
    "start_at": "nowhere",
    "steps": {
        "check": {"type": "branch", "condition": {"field": "n", "operator": "roughly"}, "on_true": "ghost", "on_false": "end"},
        "log": {"type": "action", "connector_id": "internal", "action_id": "log", "next": "end", "retry": {"max_attempts": 0}},
    },
}


@pytest.fixture
def client(monkeypatch, conn):
    monkeypatch.setenv("API_KEY", KEY)
    return TestClient(app, raise_server_exceptions=False)


def new_name():
    return f"val_{uuid.uuid4().hex[:8]}"


def create(client, definition, name=None):
    return client.post("/workflows", json={"name": name or new_name(), "definition": definition}, headers=AUTH)


def test_a_valid_definition_is_saved(client):
    assert create(client, GOOD).status_code == 201


def test_a_bad_new_workflow_is_refused_with_every_problem_and_nothing_is_stored(client, conn):
    name = new_name()
    response = create(client, BAD, name=name)
    assert response.status_code == 400
    errors = response.json()["validation_errors"]
    assert any("start_at" in e and "nowhere" in e for e in errors)
    assert any("roughly" in e for e in errors)
    assert any("ghost" in e for e in errors)
    assert any("max_attempts" in e for e in errors)
    cur = conn.cursor()
    cur.execute("SELECT count(*) AS n FROM workflows WHERE name = %s", (name,))
    assert cur.fetchone()["n"] == 0


def test_a_bad_new_version_is_refused_and_the_active_version_is_untouched(client, conn):
    created = create(client, GOOD).json()
    response = client.post(f"/workflows/{created['workflow_id']}/versions", json={"definition": BAD}, headers=AUTH)
    assert response.status_code == 400
    assert response.json()["validation_errors"]
    cur = conn.cursor()
    cur.execute("SELECT version, is_active FROM workflow_versions WHERE workflow_id = %s", (created["workflow_id"],))
    assert [(r["version"], r["is_active"]) for r in cur.fetchall()] == [(1, True)]


def test_a_good_new_version_is_saved(client):
    created = create(client, GOOD).json()
    response = client.post(f"/workflows/{created['workflow_id']}/versions", json={"definition": GOOD}, headers=AUTH)
    assert response.status_code == 201 and response.json()["version"] == 2


def test_a_loop_through_an_action_is_saved_because_polling_is_a_real_use(client):
    definition = copy.deepcopy(GOOD)
    definition["steps"]["log"]["next"] = "check"
    assert create(client, definition).status_code == 201


def test_a_loop_of_only_branch_and_delay_steps_is_refused(client):
    definition = copy.deepcopy(GOOD)
    definition["steps"]["check"]["on_false"] = "check"
    response = create(client, definition)
    assert response.status_code == 400
    assert any("loop" in e for e in response.json()["validation_errors"])


def test_the_seeded_workflow_can_be_saved_again_as_a_new_version(client):
    listed = client.get("/workflows", headers=AUTH).json()
    seeded = next(w for w in listed if w["name"] == "order_priority_workflow")
    detail = client.get(f"/workflows/{seeded['id']}", headers=AUTH).json()
    response = client.post(f"/workflows/{seeded['id']}/versions",
                           json={"definition": detail["active_version"]["definition"]}, headers=AUTH)
    assert response.status_code == 201, response.text
