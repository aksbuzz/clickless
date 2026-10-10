"""Connection credentials through the HTTP API and the worker: write-only, encrypted at rest, decrypted to run."""
import uuid

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from src.api.main import app
from tests.integration.helpers import Record, action, executions, instance, make_workflow, running_worker, start, terminal, wait_until

KEY = "k" * 32
AUTH = {"Authorization": f"Bearer {KEY}"}
PLAIN_TOKEN = "ghp_supersecret_value"


@pytest.fixture
def client(monkeypatch, conn):
    monkeypatch.setenv("API_KEY", KEY)
    monkeypatch.setenv("SECRETS_KEY", Fernet.generate_key().decode())
    return TestClient(app, raise_server_exceptions=False)


def new_name():
    return f"conn_{uuid.uuid4().hex[:8]}"


def create(client, connector_id="github", config=None, name=None):
    body = {"connector_id": connector_id, "name": name or new_name(), "config": {"token": PLAIN_TOKEN} if config is None else config}
    return client.post("/connections", json=body, headers=AUTH)


def stored_config(conn, connection_id):
    cur = conn.cursor()
    cur.execute("SELECT config FROM connections WHERE id = %s", (connection_id,))
    return cur.fetchone()["config"]


def test_the_api_never_returns_a_secret_value(client):
    created = create(client)
    assert created.status_code == 201, created.text
    connection_id = created.json()["connection_id"]

    shown = client.get(f"/connections/{connection_id}", headers=AUTH)
    assert shown.status_code == 200
    assert shown.json()["config"] == {}
    assert shown.json()["secrets_set"] == ["token"]
    assert PLAIN_TOKEN not in shown.text
    assert PLAIN_TOKEN not in client.get("/connections", headers=AUTH).text


def test_the_secret_is_encrypted_in_the_database(client, conn):
    connection_id = create(client).json()["connection_id"]
    stored = stored_config(conn, connection_id)
    assert stored["token"].startswith("enc:v1:")
    assert PLAIN_TOKEN not in str(stored)


def test_updating_without_a_secret_keeps_the_stored_one(client, conn):
    connection_id = create(client, "trello", {"api_key": "key-1", "api_token": "token-1"}).json()["connection_id"]
    before = stored_config(conn, connection_id)

    renamed = client.put(f"/connections/{connection_id}", json={"name": new_name(), "config": {}}, headers=AUTH)

    assert renamed.status_code == 200, renamed.text
    assert stored_config(conn, connection_id) == before
    assert client.get(f"/connections/{connection_id}", headers=AUTH).json()["secrets_set"] == ["api_key", "api_token"]


def test_updating_with_a_new_secret_replaces_only_that_one(client, conn):
    from src.shared.credentials import decrypt
    connection_id = create(client, "trello", {"api_key": "key-1", "api_token": "token-1"}).json()["connection_id"]
    name = client.get(f"/connections/{connection_id}", headers=AUTH).json()["name"]

    updated = client.put(f"/connections/{connection_id}", json={"name": name, "config": {"api_token": "token-2"}}, headers=AUTH)

    assert updated.status_code == 200, updated.text
    stored = stored_config(conn, connection_id)
    assert decrypt(stored["api_key"]) == "key-1"
    assert decrypt(stored["api_token"]) == "token-2"


def test_a_missing_required_secret_is_rejected_and_nothing_is_stored(client, conn):
    name = new_name()
    response = create(client, "github", {}, name=name)
    assert response.status_code == 400
    assert "Personal Access Token is required" in response.json()["validation_errors"]
    cur = conn.cursor()
    cur.execute("SELECT count(*) AS n FROM connections WHERE name = %s", (name,))
    assert cur.fetchone()["n"] == 0


def test_an_unknown_field_is_rejected(client):
    response = create(client, "github", {"token": PLAIN_TOKEN, "password": "x"})
    assert response.status_code == 400
    assert "Unknown field 'password'" in response.json()["validation_errors"]


def test_a_step_runs_with_the_decrypted_credential(client, conn):
    connection_id = create(client).json()["connection_id"]
    rec = Record()
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("record", connection_id=connection_id)}})
    iid = start(name, {})
    with running_worker({"record": rec}):
        wait_until(terminal(conn, iid))
    assert instance(conn, iid)["status"] == "completed"
    assert rec.configs[0]["token"] == PLAIN_TOKEN


def test_a_step_fails_with_a_clear_message_when_the_key_no_longer_matches(client, conn, monkeypatch):
    connection_id = create(client).json()["connection_id"]
    monkeypatch.setenv("SECRETS_KEY", Fernet.generate_key().decode())
    rec = Record()
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("record", connection_id=connection_id)}})
    iid = start(name, {})
    with running_worker({"record": rec}):
        wait_until(terminal(conn, iid))
    assert instance(conn, iid)["status"] == "failed"
    assert "SECRETS_KEY" in executions(conn, iid)[0]["error_details"]
    assert rec.calls == 0


def test_a_plaintext_connection_from_before_encryption_still_works_and_is_encrypted_on_next_save(client, conn):
    cur = conn.cursor()
    cur.execute("INSERT INTO connections (connector_id, name, config) VALUES ('github', %s, %s) RETURNING id",
                (new_name(), '{"token": "legacy-plain"}'))
    connection_id = str(cur.fetchone()["id"])

    shown = client.get(f"/connections/{connection_id}", headers=AUTH).json()
    assert shown["config"] == {} and shown["secrets_set"] == ["token"]

    rec = Record()
    name = make_workflow(conn, {"start_at": "a", "steps": {"a": action("record", connection_id=connection_id)}})
    iid = start(name, {})
    with running_worker({"record": rec}):
        wait_until(terminal(conn, iid))
    assert rec.configs[0]["token"] == "legacy-plain"

    saved = client.put(f"/connections/{connection_id}", json={"name": shown["name"], "config": {}}, headers=AUTH)
    assert saved.status_code == 200, saved.text
    assert stored_config(conn, connection_id)["token"].startswith("enc:v1:")


def test_a_connection_whose_connector_is_gone_shows_no_values_and_cannot_be_edited(client, conn):
    cur = conn.cursor()
    cur.execute("INSERT INTO connections (connector_id, name, config) VALUES ('retired_connector', %s, %s) RETURNING id",
                (new_name(), '{"token": "legacy-plain", "region": "eu"}'))
    connection_id = str(cur.fetchone()["id"])

    shown = client.get(f"/connections/{connection_id}", headers=AUTH)
    assert shown.json()["config"] == {} and shown.json()["secrets_set"] == ["region", "token"]
    assert "legacy-plain" not in shown.text

    before = stored_config(conn, connection_id)
    edited = client.put(f"/connections/{connection_id}", json={"name": "x", "config": {"token": "new"}}, headers=AUTH)
    assert edited.status_code == 400
    assert "retired_connector" in str(edited.json()["validation_errors"])
    assert stored_config(conn, connection_id) == before
