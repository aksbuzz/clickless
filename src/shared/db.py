import os
import time
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

_pool = None

def get_connection_string():
    return os.getenv("DATABASE_URL")

def get_pool(minconn=5, maxconn=20):
    global _pool
    if _pool is None:
        _pool = pool.ThreadedConnectionPool(
            minconn, maxconn,
            get_connection_string(),
            cursor_factory=RealDictCursor,
        )
    return _pool

def get_connection(retries=10, delay=0.1):
    """Get a connection from the pool, retrying briefly if the pool is exhausted."""
    for attempt in range(retries):
        try:
            return get_pool().getconn()
        except pool.PoolError:
            if attempt == retries - 1:
                raise
            time.sleep(delay)

def return_connection(conn):
    try:
        get_pool().putconn(conn)
    except Exception:
        pass
