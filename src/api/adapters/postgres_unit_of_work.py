from src.shared.base_unit_of_work import BasePostgresUnitOfWork
from src.api.adapters.postgres_repository import PostgresAPIRepository


class PostgresAPIUnitOfWork(BasePostgresUnitOfWork):
  repo: PostgresAPIRepository

  def _create_repositories(self, cursor):
    self.repo = PostgresAPIRepository(cursor)
