"""The HTTP-calling handlers must refuse internal targets and bound what they read back."""
import json
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from src.worker.handlers.action_handlers import HttpRequestHandler, SendWebhookHandler
from src.worker.handlers.postgresql import PostgresExecuteHandler, PostgresQueryHandler
from src.worker.handlers.slack import SlackSendMessageHandler


@pytest.fixture
def server():
    hits, state = [], {"body": json.dumps({"ok": True}).encode(), "content_type": "application/json"}

    class Handler(BaseHTTPRequestHandler):
        def _respond(self):
            self.rfile.read(int(self.headers.get("content-length") or 0))
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", state["content_type"])
            self.send_header("Content-Length", str(len(state["body"])))
            self.end_headers()
            self.wfile.write(state["body"])

        do_GET = do_POST = _respond

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield types.SimpleNamespace(url=f"http://127.0.0.1:{httpd.server_address[1]}", hits=hits, state=state)
    httpd.shutdown()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("OUTBOUND_ALLOW_HOSTS", "OUTBOUND_ALLOW_PRIVATE", "OUTBOUND_MAX_RESPONSE_BYTES"):
        monkeypatch.delenv(name, raising=False)


def allow_loopback(monkeypatch):
    monkeypatch.setenv("OUTBOUND_ALLOW_HOSTS", "127.0.0.1")


# ------------------------------------------------------------------ blocked by default

def test_http_request_refuses_an_internal_target_and_never_connects(server):
    result = HttpRequestHandler().execute("i", {}, config={"url": server.url + "/secret"})
    assert result.status.value == "failure"
    assert "blocked" in result.error_message.lower()
    assert server.hits == []


def test_send_webhook_refuses_an_internal_target_and_never_connects(server):
    result = SendWebhookHandler().execute("i", {"a": 1}, config={"url": server.url + "/hook"})
    assert result.status.value == "failure" and "blocked" in result.error_message.lower()
    assert server.hits == []


def test_slack_refuses_an_internal_webhook_url_and_never_connects(server):
    result = SlackSendMessageHandler().execute("i", {}, config={"webhook_url": server.url + "/slack", "text": "hi"})
    assert result.status.value == "failure" and "blocked" in result.error_message.lower()
    assert server.hits == []


@pytest.mark.parametrize("handler", [PostgresQueryHandler, PostgresExecuteHandler])
@pytest.mark.parametrize("dsn", [
    "postgresql://u:p@10.0.0.5:5432/db",
    "postgresql://u:p@8.8.8.8/db?hostaddr=10.0.0.5",         # a fine host must not hide a bad hostaddr
    "host=127.0.0.1 dbname=x",
    "dbname=x",                                       # no host means the local socket
])
def test_postgres_handlers_refuse_internal_or_unspecified_hosts(monkeypatch, handler, dsn):
    calls = []
    monkeypatch.setattr("src.worker.handlers.postgresql.psycopg2.connect", lambda *a, **k: calls.append(a))
    result = handler().execute("i", {}, config={"connection_string": dsn, "query": "SELECT 1"})
    assert result.status.value == "failure" and "blocked" in result.error_message.lower()
    assert calls == []


# ------------------------------------------------------------------ allowed when the operator says so

def test_http_request_works_for_an_allowed_host_and_returns_the_body(server, monkeypatch):
    allow_loopback(monkeypatch)
    result = HttpRequestHandler().execute("i", {}, config={"url": server.url + "/ok", "method": "GET"})
    assert result.status.value == "success"
    assert result.updated_data["http_response"] == {"status_code": 200, "body": {"ok": True}}
    assert server.hits == ["/ok"]


def test_send_webhook_and_slack_work_for_an_allowed_host(server, monkeypatch):
    allow_loopback(monkeypatch)
    assert SendWebhookHandler().execute("i", {"a": 1}, config={"url": server.url + "/hook"}).status.value == "success"
    assert SlackSendMessageHandler().execute("i", {}, config={"webhook_url": server.url + "/slack", "text": "hi"}).status.value == "success"
    assert server.hits == ["/hook", "/slack"]


# ------------------------------------------------------------------ bounded responses

def test_http_request_refuses_a_response_larger_than_the_limit(server, monkeypatch):
    allow_loopback(monkeypatch)
    monkeypatch.setenv("OUTBOUND_MAX_RESPONSE_BYTES", "1000")
    server.state["body"] = b"x" * 50_000
    result = HttpRequestHandler().execute("i", {}, config={"url": server.url + "/big"})
    assert result.status.value == "failure"
    assert "too large" in result.error_message.lower()


def test_http_request_accepts_a_response_within_the_limit(server, monkeypatch):
    allow_loopback(monkeypatch)
    monkeypatch.setenv("OUTBOUND_MAX_RESPONSE_BYTES", "1000")
    server.state["body"] = b"y" * 500
    server.state["content_type"] = "text/plain"
    result = HttpRequestHandler().execute("i", {}, config={"url": server.url + "/small"})
    assert result.status.value == "success"
    assert result.updated_data["http_response"]["body"] == "y" * 500
