"""Returned connections are kept for reuse. Reconnecting for every use costs a new backend process each time."""
import threading
import time

import pytest
from psycopg2 import pool

from src.shared import db


@pytest.fixture
def small_pool(database_url, monkeypatch):
    monkeypatch.setenv("DB_POOL_MIN", "1")
    monkeypatch.setenv("DB_POOL_MAX", "4")
    db.reset_pool()
    yield
    db.reset_pool()


def backend_pids(connections):
    pids = set()
    for conn in connections:
        cur = conn.cursor()
        cur.execute("SELECT pg_backend_pid() AS pid")
        pids.add(cur.fetchone()["pid"])
        conn.rollback()
    return pids


def test_connections_returned_to_the_pool_are_reused_not_reopened(small_pool):
    first = [db.get_connection() for _ in range(3)]
    first_pids = backend_pids(first)
    assert len(first_pids) == 3
    for conn in first:
        db.return_connection(conn)

    second = [db.get_connection() for _ in range(3)]
    try:
        assert backend_pids(second) == first_pids        # the same three backends, not three new ones
    finally:
        for conn in second:
            db.return_connection(conn)


def test_the_pool_never_exceeds_its_maximum_and_a_caller_waits_then_gives_up(small_pool):
    held = [db.get_connection() for _ in range(4)]
    try:
        started = time.monotonic()
        with pytest.raises(pool.PoolError):
            db.get_connection(timeout=0.3)
        assert 0.25 <= time.monotonic() - started < 2.0
    finally:
        for conn in held:
            db.return_connection(conn)


def test_a_waiting_caller_gets_a_connection_as_soon_as_one_is_returned(small_pool):
    held = [db.get_connection() for _ in range(4)]
    threading.Timer(0.3, db.return_connection, args=(held[0],)).start()
    started = time.monotonic()
    waiter = db.get_connection(timeout=5)
    try:
        assert 0.25 <= time.monotonic() - started < 2.0
    finally:
        db.return_connection(waiter)
        for conn in held[1:]:
            db.return_connection(conn)


def test_many_threads_can_share_a_small_pool(small_pool):
    """Twelve threads, four connections: nobody fails, because callers wait for a free one."""
    results = []

    def work():
        with db.db_cursor() as cur:
            cur.execute("SELECT pg_sleep(0.05), 1 AS one")
            results.append(cur.fetchone()["one"])

    threads = [threading.Thread(target=work) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert results == [1] * 12
