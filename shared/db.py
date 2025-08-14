import os
import psycopg2
from contextlib import contextmanager

@contextmanager
def get_db_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    conn = psycopg2.connect(database_url)
    try:
        yield conn
    finally:
        conn.close()
