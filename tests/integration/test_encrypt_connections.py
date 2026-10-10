"""python -m src.api.encrypt_connections: encrypt legacy plaintext credentials and rotate the key."""
import json
import uuid

import pytest
from cryptography.fernet import Fernet

from src.api import encrypt_connections
from src.shared import credentials
from src.shared.db import db_cursor


def new_key():
    return Fernet.generate_key().decode()


def add(conn, connector_id, config, name=None):
    cur = conn.cursor()
    cur.execute("INSERT INTO connections (connector_id, name, config) VALUES (%s, %s, %s) RETURNING id",
                (connector_id, name or f"enc_{uuid.uuid4().hex[:8]}", json.dumps(config)))
    return str(cur.fetchone()["id"])


def config_of(conn, connection_id):
    cur = conn.cursor()
    cur.execute("SELECT config FROM connections WHERE id = %s", (connection_id,))
    return cur.fetchone()["config"]


@pytest.fixture
def key(monkeypatch, conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM connections")
    k = new_key()
    monkeypatch.setenv("SECRETS_KEY", k)
    return k


def run():
    with db_cursor() as cur:
        return encrypt_connections.reencrypt_all(cur)


def test_plaintext_credentials_are_encrypted(conn, key):
    connection_id = add(conn, "github", {"token": "ghp_plain"})
    result = run()
    stored = config_of(conn, connection_id)
    assert stored["token"].startswith("enc:v1:") and "ghp_plain" not in str(stored)
    assert credentials.decrypt(stored["token"]) == "ghp_plain"
    assert result.updated == 1 and result.skipped == []


def test_only_secret_fields_are_touched(conn, key):
    connection_id = add(conn, "github", {"token": "ghp_plain", "note": "keep me"})
    run()
    assert config_of(conn, connection_id)["note"] == "keep me"


def test_rotation_moves_everything_to_the_new_key(conn, key, monkeypatch):
    connection_id = add(conn, "trello", {"api_key": "k1", "api_token": "t1"})
    run()                                                    # encrypted with the first key
    new = new_key()
    monkeypatch.setenv("SECRETS_KEY", f"{new},{key}")
    run()                                                    # re-encrypted with the new key
    monkeypatch.setenv("SECRETS_KEY", new)                   # the old key is no longer needed
    stored = config_of(conn, connection_id)
    assert credentials.decrypt(stored["api_key"]) == "k1" and credentials.decrypt(stored["api_token"]) == "t1"


def test_a_connection_whose_connector_is_gone_is_skipped_and_reported(conn, key):
    gone = add(conn, "retired_connector", {"token": "left alone"})
    result = run()
    assert config_of(conn, gone) == {"token": "left alone"}
    assert result.skipped == [gone]


def test_nothing_changes_if_a_stored_value_cannot_be_decrypted(conn, key, monkeypatch):
    good = add(conn, "github", {"token": "ghp_plain"})
    run()
    before = config_of(conn, good)
    other = add(conn, "slack", {"webhook_url": credentials.PREFIX + "this-was-not-made-with-our-key"})
    plain = add(conn, "postgresql", {"connection_string": "postgresql://u:p@h/db"})
    with pytest.raises(credentials.SecretDecryptionError):
        run()
    assert config_of(conn, good) == before
    assert config_of(conn, plain) == {"connection_string": "postgresql://u:p@h/db"}
    assert config_of(conn, other)["webhook_url"].endswith("this-was-not-made-with-our-key")


def test_running_it_twice_is_harmless(conn, key):
    connection_id = add(conn, "github", {"token": "ghp_plain"})
    run()
    run()
    assert credentials.decrypt(config_of(conn, connection_id)["token"]) == "ghp_plain"
