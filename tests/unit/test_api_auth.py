"""API-key authentication: deny by default, fail closed."""
import uuid

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from src.api import auth
from src.api.dependencies import get_service
from src.api.main import app

KEY = "k" * 32
SOME_ID = str(uuid.uuid4())

# Routes that must stay reachable without the API key: the container readiness probe, and the
# provider webhooks, which authenticate with their own signatures instead.
PUBLIC_ROUTES = {"/ready", "/triggers/{connector_id}/webhook"}

PROTECTED = [
    ("GET", "/workflows"),
    ("POST", "/workflows"),
    ("GET", f"/workflows/{SOME_ID}"),
    ("POST", "/workflows/some_name/run"),
    ("POST", "/webhooks/some_name"),
    ("GET", "/instances"),
    ("GET", f"/instances/{SOME_ID}"),
    ("POST", f"/instances/{SOME_ID}/cancel"),
    ("POST", f"/instances/{SOME_ID}/events"),
    ("GET", "/connections"),
    ("GET", f"/connections/{SOME_ID}"),
    ("DELETE", f"/connections/{SOME_ID}"),
    ("GET", "/connectors"),
    ("GET", "/metrics"),
    ("GET", "/health"),
]


class FakeService:
    def list_workflows(self):
        return []


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", KEY)
    app.dependency_overrides[get_service] = lambda: FakeService()
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("method,path", PROTECTED)
def test_protected_route_rejects_a_request_without_a_key(client, method, path):
    response = client.request(method, path, json={})
    assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("header", ["Bearer wrong-key-wrong-key-wrong-key-xx", "Basic " + KEY, "Bearer ", KEY, "bearer"])
def test_wrong_or_malformed_credentials_are_rejected(client, header):
    assert client.get("/workflows", headers={"Authorization": header}).status_code == 401


def test_correct_key_is_accepted(client):
    response = client.get("/workflows", headers={"Authorization": f"Bearer {KEY}"})
    assert response.status_code == 200
    assert response.json() == []


def test_every_route_requires_the_key_except_the_public_allowlist():
    unprotected = [
        f"{sorted(route.methods)} {route.path}"
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path not in PUBLIC_ROUTES
        and auth.require_api_key not in [dep.call for dep in route.dependant.dependencies]
    ]
    assert unprotected == []


def test_readiness_probe_is_public(client, monkeypatch):
    class DummyCursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, *args):
            pass

    monkeypatch.setattr("src.api.routers.health.db_cursor", lambda: DummyCursor())
    assert client.get("/ready").status_code == 200


def test_provider_webhook_registration_check_is_public(client):
    assert client.head("/triggers/github/webhook").status_code == 200


def test_requests_fail_closed_when_no_key_is_configured(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    app.dependency_overrides[get_service] = lambda: FakeService()
    try:
        anon = TestClient(app, raise_server_exceptions=False)
        assert anon.get("/workflows").status_code == 503
        assert anon.get("/workflows", headers={"Authorization": "Bearer anything"}).status_code == 503
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("value", [None, "", "   ", "short-key"])
def test_startup_check_rejects_a_missing_or_weak_key(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("API_KEY", raising=False)
    else:
        monkeypatch.setenv("API_KEY", value)
    with pytest.raises(RuntimeError, match="API_KEY"):
        auth.validate_auth_config()


def test_startup_check_accepts_a_long_key(monkeypatch):
    monkeypatch.setenv("API_KEY", KEY)
    auth.validate_auth_config()
