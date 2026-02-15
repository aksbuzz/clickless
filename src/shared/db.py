import os
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

_pool = None

def get_connection_string():
    return os.getenv("DATABASE_URL")

def get_pool(minconn=2, maxconn=10):
    global _pool
    if _pool is None:
        _pool = pool.ThreadedConnectionPool(
            minconn, maxconn,
            get_connection_string(),
            cursor_factory=RealDictCursor,
        )
    return _pool

def get_connection():
    return get_pool().getconn()

def return_connection(conn):
    get_pool().putconn(conn)
