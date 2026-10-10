"""The API and the worker refuse to start without a usable SECRETS_KEY, instead of failing on the first connection."""
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from src.api.main import app
from src.shared.credentials import SecretsKeyError
from src.worker import main as worker_main


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("API_KEY", "k" * 32)


@pytest.mark.parametrize("value", [None, "", "   ", "not-a-key"])
def test_the_api_does_not_start_without_a_valid_key(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("SECRETS_KEY", raising=False)
    else:
        monkeypatch.setenv("SECRETS_KEY", value)
    with pytest.raises(SecretsKeyError):
        with TestClient(app):
            pass


def test_the_api_starts_with_a_valid_key(monkeypatch):
    monkeypatch.setenv("SECRETS_KEY", Fernet.generate_key().decode())
    with TestClient(app):
        pass


@pytest.mark.parametrize("value", [None, "not-a-key"])
def test_the_worker_does_not_start_without_a_valid_key(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("SECRETS_KEY", raising=False)
    else:
        monkeypatch.setenv("SECRETS_KEY", value)
    with pytest.raises(SecretsKeyError):
        worker_main.main()
