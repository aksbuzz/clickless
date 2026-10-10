"""The connection pool is small by default, configurable, and can be reset."""
import pytest

from src.shared import db


class FakePool:
    created = []

    def __init__(self, minconn, maxconn, dsn, **kwargs):
        self.args = (minconn, maxconn, dsn)
        self.minconn, self.maxconn = minconn, maxconn
        self.closed = False
        FakePool.created.append(self)

    def closeall(self):
        self.closed = True


@pytest.fixture(autouse=True)
def fake_pool(monkeypatch):
    FakePool.created = []
    monkeypatch.setattr(db.pool, "ThreadedConnectionPool", FakePool)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.delenv("DB_POOL_MIN", raising=False)
    monkeypatch.delenv("DB_POOL_MAX", raising=False)
    db._pool = None
    yield
    db._pool = None


def test_the_default_pool_is_small():
    db.get_pool()
    assert FakePool.created[0].args == (1, 10, "postgresql://u:p@h/d")


def test_pool_sizes_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("DB_POOL_MIN", "2")
    monkeypatch.setenv("DB_POOL_MAX", "7")
    db.get_pool()
    assert FakePool.created[0].args[:2] == (2, 7)


def test_the_pool_is_created_once():
    assert db.get_pool() is db.get_pool()
    assert len(FakePool.created) == 1


def test_reset_pool_closes_it_and_the_next_use_builds_a_new_one():
    first = db.get_pool()
    db.reset_pool()
    assert first.closed is True
    assert db.get_pool() is not first
    assert len(FakePool.created) == 2


def test_reset_pool_without_a_pool_is_a_no_op():
    db.reset_pool()


def test_idle_connections_are_kept_up_to_the_maximum_not_just_the_minimum():
    # psycopg2 closes returned connections beyond `minconn`, which would reconnect on almost every use.
    pool = db.get_pool()
    assert pool.minconn == pool.maxconn == 10
    assert pool.args[0] == 1          # but only the configured minimum is opened up front
