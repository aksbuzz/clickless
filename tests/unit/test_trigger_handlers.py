"""Webhook verification must fail closed: no configured secret means no accepted request."""
import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_service
from src.api.main import app
from src.api.trigger_handlers.github import GitHubTriggerHandler
from src.api.trigger_handlers.slack import SlackTriggerHandler
from src.api.trigger_handlers.trello import TrelloTriggerHandler

BODY = json.dumps({"zen": "Keep it logically awesome."}).encode()


# ------------------------------------------------------------------ GitHub

def github_signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.mark.parametrize("config", [{}, {"webhook_secret": ""}, {"webhook_secret": None}])
def test_github_rejects_everything_when_no_secret_is_configured(config):
    headers = {"x-hub-signature-256": github_signature("anything", BODY)}
    result = GitHubTriggerHandler().validate_webhook(headers, BODY, config)
    assert result.is_valid is False


def test_github_accepts_a_correct_signature():
    headers = {"x-hub-signature-256": github_signature("s3cret", BODY)}
    assert GitHubTriggerHandler().validate_webhook(headers, BODY, {"webhook_secret": "s3cret"}).is_valid


@pytest.mark.parametrize("headers", [
    {},
    {"x-hub-signature-256": ""},
    {"x-hub-signature-256": github_signature("other", BODY)},
    {"x-hub-signature-256": github_signature("s3cret", b"tampered")},
    {"x-hub-signature-256": "sha256=" + chr(0xE9)},   # non-ASCII must be a rejection, not a crash
])
def test_github_rejects_a_missing_or_wrong_signature(headers):
    assert not GitHubTriggerHandler().validate_webhook(headers, BODY, {"webhook_secret": "s3cret"}).is_valid


# ------------------------------------------------------------------ Slack

def slack_headers(secret: str, body: bytes, timestamp: float | None = None) -> dict:
    ts = str(int(timestamp if timestamp is not None else time.time()))
    base = f"v0:{ts}:{body.decode()}".encode()
    return {"x-slack-request-timestamp": ts, "x-slack-signature": "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()}


CHALLENGE = json.dumps({"type": "url_verification", "challenge": "abc123"}).encode()


@pytest.mark.parametrize("config", [{}, {"signing_secret": ""}])
def test_slack_rejects_everything_when_no_secret_is_configured(config):
    handler = SlackTriggerHandler()
    assert not handler.validate_webhook(slack_headers("x", BODY), BODY, config).is_valid
    result = handler.validate_webhook(slack_headers("x", CHALLENGE), CHALLENGE, config)
    assert not result.is_valid and result.challenge_response is None


def test_slack_does_not_answer_an_unsigned_url_verification_challenge():
    result = SlackTriggerHandler().validate_webhook({}, CHALLENGE, {"signing_secret": "s3cret"})
    assert not result.is_valid
    assert result.challenge_response is None


def test_slack_answers_a_correctly_signed_url_verification_challenge():
    result = SlackTriggerHandler().validate_webhook(slack_headers("s3cret", CHALLENGE), CHALLENGE, {"signing_secret": "s3cret"})
    assert result.is_valid and result.challenge_response == "abc123"


def test_slack_accepts_a_correctly_signed_event():
    assert SlackTriggerHandler().validate_webhook(slack_headers("s3cret", BODY), BODY, {"signing_secret": "s3cret"}).is_valid


def test_slack_rejects_a_wrong_signature_and_a_stale_timestamp():
    handler, config = SlackTriggerHandler(), {"signing_secret": "s3cret"}
    assert not handler.validate_webhook(slack_headers("other", BODY), BODY, config).is_valid
    assert not handler.validate_webhook(slack_headers("s3cret", BODY, timestamp=time.time() - 3600), BODY, config).is_valid
    non_ascii = {**slack_headers("s3cret", BODY), "x-slack-signature": "v0=" + chr(0xE9)}
    assert not handler.validate_webhook(non_ascii, BODY, config).is_valid


# ------------------------------------------------------------------ Trello

CALLBACK = "https://example.test/triggers/trello/webhook"


def trello_headers(secret: str, body: bytes, callback: str = CALLBACK) -> dict:
    digest = hmac.new(secret.encode(), body + callback.encode(), hashlib.sha1).digest()
    return {"x-trello-webhook": base64.b64encode(digest).decode()}


TRELLO_CONFIG = {"api_secret": "s3cret", "callback_url": CALLBACK}


@pytest.mark.parametrize("config", [{}, {"api_secret": "s3cret"}, {"callback_url": CALLBACK}, {"api_secret": "", "callback_url": CALLBACK}])
def test_trello_rejects_everything_when_it_is_not_fully_configured(config):
    assert not TrelloTriggerHandler().validate_webhook(trello_headers("s3cret", BODY), BODY, config).is_valid


def test_trello_accepts_a_correct_signature():
    assert TrelloTriggerHandler().validate_webhook(trello_headers("s3cret", BODY), BODY, TRELLO_CONFIG).is_valid


@pytest.mark.parametrize("headers", [
    {},
    {"x-trello-webhook": ""},
    trello_headers("other", BODY),
    trello_headers("s3cret", BODY, callback="https://evil.test/hook"),
    trello_headers("s3cret", b"tampered"),
])
def test_trello_rejects_a_missing_or_wrong_signature(headers):
    assert not TrelloTriggerHandler().validate_webhook(headers, BODY, TRELLO_CONFIG).is_valid


# ------------------------------------------------------------------ through the HTTP route

class IdleService:
    def process_external_trigger(self, event, handler):
        return []


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", "k" * 32)
    for name in ("GITHUB_WEBHOOK_SECRET", "SLACK_SIGNING_SECRET", "TRELLO_API_SECRET", "TRELLO_CALLBACK_URL"):
        monkeypatch.delenv(name, raising=False)
    app.dependency_overrides[get_service] = lambda: IdleService()
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("connector", ["github", "slack", "trello"])
def test_route_rejects_unsigned_webhooks_when_the_secret_is_not_configured(client, connector):
    response = client.post(f"/triggers/{connector}/webhook", content=BODY)
    assert response.status_code == 401


def test_route_accepts_a_signed_github_ping_when_the_secret_is_configured(client, monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cret")
    response = client.post("/triggers/github/webhook", content=BODY,
                           headers={"x-hub-signature-256": github_signature("s3cret", BODY), "x-github-event": "ping"})
    assert response.status_code == 200


def test_route_accepts_a_signed_trello_event_when_configured(client, monkeypatch):
    monkeypatch.setenv("TRELLO_API_SECRET", "s3cret")
    monkeypatch.setenv("TRELLO_CALLBACK_URL", CALLBACK)
    response = client.post("/triggers/trello/webhook", content=BODY, headers=trello_headers("s3cret", BODY))
    assert response.status_code == 200
