"""Worker process configuration comes from the environment, with safe defaults."""
import os

import pytest

from src.worker.main import size_connection_pool, worker_settings

NAMES = ("WORKER_CONCURRENCY", "JOB_LEASE_SECONDS", "WORKER_IDLE_POLL_SECONDS", "WORKER_METRICS_PORT", "RETENTION_DAYS",
         "DB_POOL_MAX", "DB_POOL_MIN")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)


def test_defaults():
    assert worker_settings() == {"concurrency": 8, "lease_seconds": 300.0, "idle_poll": 5.0, "metrics_port": 9100,
                                 "retention_days": 30}


def test_environment_overrides(monkeypatch):
    monkeypatch.setenv("WORKER_CONCURRENCY", "3")
    monkeypatch.setenv("JOB_LEASE_SECONDS", "60")
    monkeypatch.setenv("WORKER_IDLE_POLL_SECONDS", "1.5")
    monkeypatch.setenv("WORKER_METRICS_PORT", "9200")
    monkeypatch.setenv("RETENTION_DAYS", "7")
    assert worker_settings() == {"concurrency": 3, "lease_seconds": 60.0, "idle_poll": 1.5, "metrics_port": 9200,
                                 "retention_days": 7}


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


def test_retention_can_be_switched_off_with_zero(monkeypatch):
    monkeypatch.setenv("RETENTION_DAYS", "0")
    assert worker_settings()["retention_days"] == 0


@pytest.mark.parametrize("value", ["-1", "1.5", "a month", ""])
def test_a_nonsense_retention_period_is_rejected_instead_of_guessed(monkeypatch, value):
    monkeypatch.setenv("RETENTION_DAYS", value)
    with pytest.raises(ValueError, match="RETENTION_DAYS"):
        worker_settings()


def test_no_housekeeper_is_started_when_retention_is_off():
    import threading
    from src.worker.main import start_housekeeper
    assert start_housekeeper({"retention_days": 0}, threading.Event()) is None


def test_the_housekeeper_thread_starts_and_stops_with_the_worker():
    import threading
    from src.worker.main import start_housekeeper
    stop = threading.Event()
    thread = start_housekeeper({"retention_days": 30}, stop)
    assert thread.is_alive()
    stop.set()
    thread.join(timeout=3)
    assert not thread.is_alive()
