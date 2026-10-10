"""Worker process: claims jobs from PostgreSQL and runs workflow steps.

    python -m src.worker.main

Settings (environment): WORKER_CONCURRENCY (threads, default 8), JOB_LEASE_SECONDS (how long a job is held
before another worker may take it, default 300), WORKER_IDLE_POLL_SECONDS (safety wake-up, default 5),
WORKER_METRICS_PORT (Prometheus endpoint, default 9100), DB_POOL_MAX (default WORKER_CONCURRENCY + 2, at most 16),
RETENTION_DAYS (finished runs older than this are deleted, default 30, 0 keeps them forever).
SECRETS_KEY is required: it decrypts the credentials stored in connections.
"""
import os
import signal
import threading

from prometheus_client import start_http_server

from src.engine.retention import DEFAULT_RETENTION_DAYS, Housekeeper
from src.engine.worker import Worker
from src.shared import credentials
from src.shared.db import reset_pool
from src.shared.logging_config import log


def _number(name: str, default: float, convert=float, minimum: float = 0.0):
    value = convert(os.getenv(name, default))
    if value <= minimum:
        raise ValueError(f"{name} must be greater than {minimum:g}, got {value:g}")
    return value


def _retention_days() -> int:
    raw = os.getenv("RETENTION_DAYS")
    if raw is None:
        return DEFAULT_RETENTION_DAYS
    try:
        days = int(raw)
    except ValueError:
        raise ValueError(f"RETENTION_DAYS must be a whole number of days (0 turns retention off), got {raw!r}") from None
    if days < 0:
        raise ValueError(f"RETENTION_DAYS must be 0 or more, got {days}")
    return days


def worker_settings() -> dict:
    return {
        "concurrency": _number("WORKER_CONCURRENCY", 8, int),
        "lease_seconds": _number("JOB_LEASE_SECONDS", 300.0),
        "idle_poll": _number("WORKER_IDLE_POLL_SECONDS", 5.0),
        "metrics_port": _number("WORKER_METRICS_PORT", 9100, int),
        "retention_days": _retention_days(),
    }


MAX_DEFAULT_POOL = 16


def size_connection_pool(concurrency: int) -> None:
    """A step holds a database connection only for a few milliseconds and threads wait for a free one, so the
    pool does not need a connection per thread; capping it keeps a high WORKER_CONCURRENCY from exceeding
    PostgreSQL's connection limit. Must run before the pool is first used."""
    os.environ.setdefault("DB_POOL_MAX", str(min(concurrency + 2, MAX_DEFAULT_POOL)))


def start_housekeeper(settings: dict, stop: threading.Event):
    """Delete finished runs older than RETENTION_DAYS in the background. Returns the thread, or None if retention is off."""
    if not settings["retention_days"]:
        log.info("Retention is off (RETENTION_DAYS=0): finished runs are kept forever")
        return None
    thread = threading.Thread(target=Housekeeper(settings["retention_days"]).run, args=(stop,), name="retention", daemon=True)
    thread.start()
    return thread


def main() -> None:
    credentials.check_configured()   # steps cannot read their connections without it
    settings = worker_settings()
    size_connection_pool(settings["concurrency"])

    from src.worker.registry import get_registry   # imports every handler

    start_http_server(settings["metrics_port"])
    worker = Worker(get_registry(), concurrency=settings["concurrency"], lease_seconds=settings["lease_seconds"],
                    idle_poll=settings["idle_poll"])

    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    log.info("Worker started", **settings)
    start_housekeeper(settings, stop)
    worker.run(stop)
    reset_pool()
    log.info("Worker stopped")


if __name__ == "__main__":
    main()
