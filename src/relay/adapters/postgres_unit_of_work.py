import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Iterable, List

from src.relay.domain.models import OutboxMessage
from src.relay.domain.ports import OutboxRepositoryPort, UnitOfWorkPort

class PostgresOutboxRepository(OutboxRepositoryPort):
  def __init__(self, cursor):
    self.cursor = cursor

  def fetch_due_messages(self, limit: int) -> List[OutboxMessage]:
    self.cursor.execute(
      """
      SELECT id, destination, payload, publish_at
      FROM outbox
      WHERE processed_at IS NULL AND publish_at <= NOW()
      ORDER BY publish_at
      LIMIT %s
      """,
      (limit,)
    )
    rows = self.cursor.fetchall()

    return [
      OutboxMessage(
        id=str(r["id"]),
        destination=r["destination"],
        payload=r["payload"],
        publish_at=r["publish_at"],
      )
      for r in rows
    ]

  def mark_processed(self, ids: Iterable[str]) -> None:
    ids = list(ids)
    if not ids:
      return
    
    self.cursor.execute(
      """
      UPDATE outbox
      SET processed_at = NOW()
      WHERE id = ANY(%s::uuid[])
      """,
      (ids,)
    )

class PostgresUnitOfWork(UnitOfWorkPort):
  outbox: PostgresOutboxRepository

  def __init__(self, conn_string: str):
    self.conn_string = conn_string

  def __enter__(self):
    self.conn = psycopg2.connect(self.conn_string, cursor_factory=RealDictCursor)
    self.cursor = self.conn.cursor()
    
    self.outbox = PostgresOutboxRepository(self.cursor)
    return self
  
  def __exit__(self, exc_type, exc_val, exc_tb):
    if exc_type:
      self.rollback()
    else:
      self.commit()
    
    self.outbox = None
    self.cursor.close()
    self.conn.close()

  def commit(self):
    self.conn.commit()

  def rollback(self):
    self.conn.rollback()