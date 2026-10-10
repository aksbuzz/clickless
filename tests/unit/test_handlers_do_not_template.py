"""Templates are resolved once, by the engine. A handler must use its config exactly as it receives it, so a value
that itself contains {{...}} can never be resolved a second time."""
from contextlib import contextmanager

from src.worker.handlers.github import GitHubAddCommentHandler, GitHubCreateIssueHandler
from src.worker.handlers.postgresql import PostgresExecuteHandler, PostgresQueryHandler
from src.worker.handlers.slack import SlackSendMessageHandler
from src.worker.handlers.trello import TrelloAddCommentHandler, TrelloCreateCardHandler

LITERAL = "{{secret}}"
DATA = {"secret": "LEAKED"}


class FakeResponse:
    is_success = True
    status_code = 200

    def json(self):
        return {"number": 1, "html_url": "u", "id": "1", "url": "u"}


def capture_post(monkeypatch, module):
    sent = {}

    def post(url, headers=None, json=None, params=None, timeout=None):
        sent.update(url=url, json=json)
        return FakeResponse()

    monkeypatch.setattr(f"src.worker.handlers.{module}.httpx.post", post)
    return sent


def test_github_handlers_use_their_config_as_received(monkeypatch):
    sent = capture_post(monkeypatch, "github")
    base = {"token": "t", "owner": "o", "repo": "r"}
    GitHubCreateIssueHandler().execute("i", dict(DATA), config={**base, "title": LITERAL, "body": LITERAL})
    assert sent["json"] == {"title": LITERAL, "body": LITERAL}
    GitHubAddCommentHandler().execute("i", dict(DATA), config={**base, "issue_number": 1, "body": LITERAL})
    assert sent["json"] == {"body": LITERAL}


def test_trello_handlers_use_their_config_as_received(monkeypatch):
    sent = capture_post(monkeypatch, "trello")
    base = {"api_key": "k", "api_token": "t"}
    TrelloCreateCardHandler().execute("i", dict(DATA), config={**base, "list_id": "l", "name": LITERAL, "description": LITERAL})
    assert sent["json"] == {"idList": "l", "name": LITERAL, "desc": LITERAL}
    TrelloAddCommentHandler().execute("i", dict(DATA), config={**base, "card_id": "c", "text": LITERAL})
    assert sent["json"] == {"text": LITERAL}


def test_slack_handler_uses_its_config_as_received(monkeypatch):
    sent = {}

    @contextmanager
    def stream(method, url, json=None, timeout=None):
        sent["json"] = json
        yield FakeResponse()

    monkeypatch.setattr("src.worker.handlers.slack.httpx.stream", stream)
    SlackSendMessageHandler().execute("i", dict(DATA), config={"webhook_url": "http://8.8.8.8/hook", "text": LITERAL})
    assert sent["json"] == {"text": LITERAL}


def test_postgres_handlers_pass_params_through_untouched(monkeypatch):
    seen = {}

    class Cursor:
        rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, query, params=None):
            seen.update(query=query, params=params)

        def fetchall(self):
            return []

    class Connection:
        def cursor(self, **kwargs):
            return Cursor()

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr("src.worker.handlers.postgresql.psycopg2.connect", lambda *a, **k: Connection())
    monkeypatch.setenv("OUTBOUND_ALLOW_PRIVATE", "true")
    for handler in (PostgresQueryHandler, PostgresExecuteHandler):
        handler().execute("i", dict(DATA), config={"connection_string": "postgresql://h/d", "query": "SELECT %s", "params": [LITERAL]})
        assert seen["params"] == [LITERAL]


def test_the_sql_handlers_name_the_keys_the_engine_must_never_template():
    for handler in (PostgresQueryHandler, PostgresExecuteHandler):
        assert set(handler.untemplated_keys) == {"query", "connection_string"}
