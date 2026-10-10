import os
import threading
from contextlib import contextmanager

from psycopg2 import pool
from psycopg2.extras import RealDictCursor

DEFAULT_WAIT_SECONDS = 30.0

_pool = None
_slots = None      # one slot per connection the pool may hold; callers wait here instead of failing
_lock = threading.Lock()


def get_connection_string():
    return os.getenv("DATABASE_URL")


def get_pool():
    """One small pool per process. Size it with DB_POOL_MIN / DB_POOL_MAX (defaults 1 and 10)."""
    global _pool, _slots
    with _lock:
        if _pool is None:
            created = pool.ThreadedConnectionPool(
                int(os.getenv("DB_POOL_MIN", "1")), int(os.getenv("DB_POOL_MAX", "10")),
                get_connection_string(),
                cursor_factory=RealDictCursor,
            )
            # psycopg2 keeps at most `minconn` idle connections and closes the rest when they are returned, so
            # under load nearly every use would open a new backend process. Keep up to the maximum instead. Only
            # DB_POOL_MIN connections are opened up front; the others are still opened on demand.
            created.minconn = created.maxconn
            _slots = threading.BoundedSemaphore(created.maxconn)
            _pool = created
        return _pool


def reset_pool():
    """Close the pool; the next use builds a new one. Used on shutdown and by tests."""
    global _pool, _slots
    with _lock:
        if _pool is not None:
            _pool.closeall()
        _pool, _slots = None, None


def get_connection(timeout: float = DEFAULT_WAIT_SECONDS):
    """Take a connection from the pool. When all of them are in use, wait up to `timeout` seconds for one to be
    returned and then raise PoolError. A step holds a connection only briefly, so many threads can share a small pool."""
    current = get_pool()
    slots = _slots
    if not slots.acquire(timeout=timeout):
        raise pool.PoolError("timed out waiting for a database connection")
    try:
        return current.getconn()
    except BaseException:
        slots.release()
        raise


def return_connection(conn):
    current, slots = _pool, _slots
    try:
        if current is not None:
            current.putconn(conn)
    except Exception:
        pass
    finally:
        if slots is not None:
            try:
                slots.release()
            except ValueError:      # a connection from a pool that was reset
                pass


@contextmanager
def db_cursor():
    """Context manager that provides a cursor with automatic commit/rollback and connection return."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        return_connection(conn)
