from abc import ABC, abstractmethod

from src.shared.db import get_connection, return_connection


class BasePostgresUnitOfWork(ABC):
  @abstractmethod
  def _create_repositories(self, cursor):
    """Subclasses create their specific repository instances here."""
    ...

  def __enter__(self):
    self.conn = get_connection()
    self.cursor = self.conn.cursor()
    self._create_repositories(self.cursor)
    return self

  def __exit__(self, exc_type, exc_val, exc_tb):
    if exc_type:
      self.rollback()
    else:
      self.commit()
    self.cursor.close()
    return_connection(self.conn)

  def commit(self):
    self.conn.commit()

  def rollback(self):
    self.conn.rollback()
