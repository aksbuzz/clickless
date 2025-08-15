from typing import Iterable, List

from src.relay.domain.models import OutboxMessage
from src.relay.domain.ports import OutboxRepositoryPort

class PostgresOutboxRepository(OutboxRepositoryPort):
  def __init__(self, conn_factory):
    self.conn_factory = conn_factory

  def fetch_due_messages(self, limit: int) -> List[OutboxMessage]:
    with self.conn_factory() as db_conn:
      with db_conn.cursor() as cur:
        cur.execute(
          """
          SELECT id, destination, payload, publish_at
          FROM outbox
          WHERE processed_at IS NULL AND publish_at <= NOW()
          ORDER BY publish_at
          LIMIT %s
          """,
          (limit,)
        )
        rows = cur.fetchall()

    return [
      OutboxMessage(
        id=str(r[0]),
        destination=r[1],
        payload=r[2],
        publish_at=r[3],
      )
      for r in rows
    ]

  def mark_processed(self, ids: Iterable[str]) -> None:
    ids = list(ids)
    if not ids:
      return
    with self.conn_factory() as db_conn:
      with db_conn.cursor() as cur:
        cur.execute(
          """
          UPDATE outbox
          SET processed_at = NOW()
          WHERE id = ANY(%s::uuid[])
          """,
          (ids,)
        )

      db_conn.commit()
