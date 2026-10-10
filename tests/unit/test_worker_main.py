"""Worker process configuration comes from the environment, with safe defaults."""
import os

import pytest

from src.worker.main import size_connection_pool, worker_settings

NAMES = ("WORKER_CONCURRENCY", "JOB_LEASE_SECONDS", "WORKER_IDLE_POLL_SECONDS", "WORKER_METRICS_PORT", "DB_POOL_MAX", "DB_POOL_MIN")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)


def test_defaults():
    assert worker_settings() == {"concurrency": 8, "lease_seconds": 300.0, "idle_poll": 5.0, "metrics_port": 9100}


def test_environment_overrides(monkeypatch):
    monkeypatch.setenv("WORKER_CONCURRENCY", "3")
    monkeypatch.setenv("JOB_LEASE_SECONDS", "60")
    monkeypatch.setenv("WORKER_IDLE_POLL_SECONDS", "1.5")
    monkeypatch.setenv("WORKER_METRICS_PORT", "9200")
    assert worker_settings() == {"concurrency": 3, "lease_seconds": 60.0, "idle_poll": 1.5, "metrics_port": 9200}


@pytest.mark.parametrize("name,value", [("WORKER_CONCURRENCY", "0"), ("WORKER_CONCURRENCY", "-2"), ("JOB_LEASE_SECONDS", "0")])
def test_nonsense_values_are_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        worker_settings()


def test_the_database_pool_is_sized_for_the_threads_plus_headroom():
    size_connection_pool(8)
    assert os.environ["DB_POOL_MAX"] == "10"


def test_the_database_pool_is_capped_however_many_threads_there_are():
    # A step holds a connection only for a few milliseconds, and callers wait for a free one, so 128 threads
    # must not ask PostgreSQL for 130 connections (its default limit is 100).
    size_connection_pool(128)
    assert os.environ["DB_POOL_MAX"] == "16"


def test_an_explicit_pool_size_is_left_alone(monkeypatch):
    monkeypatch.setenv("DB_POOL_MAX", "25")
    size_connection_pool(8)
    assert os.environ["DB_POOL_MAX"] == "25"
