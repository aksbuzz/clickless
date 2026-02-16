import threading
from abc import ABC, abstractmethod

from src.shared.db import get_connection, return_connection


class BasePostgresUnitOfWork(ABC):
  def __init__(self):
    self._local = threading.local()

  @abstractmethod
  def _create_repositories(self, cursor):
    """Subclasses create their specific repository instances here."""
    ...

  def __enter__(self):
    conn = get_connection()
    cursor = conn.cursor()
    self._local.conn = conn
    self._local.cursor = cursor
    self._create_repositories(cursor)
    return self

  def __exit__(self, exc_type, exc_val, exc_tb):
    conn = self._local.conn
    cursor = self._local.cursor
    try:
      if exc_type:
        conn.rollback()
      else:
        conn.commit()
    except Exception:
      conn.rollback()
      raise
    finally:
      cursor.close()
      return_connection(conn)

  def commit(self):
    self._local.conn.commit()

  def rollback(self):
    self._local.conn.rollback()
