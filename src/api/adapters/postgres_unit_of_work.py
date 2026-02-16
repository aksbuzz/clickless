from src.shared.base_unit_of_work import BasePostgresUnitOfWork
from src.api.adapters.postgres_repository import PostgresAPIRepository


class PostgresAPIUnitOfWork(BasePostgresUnitOfWork):

  def _create_repositories(self, cursor):
    self._local.repo = PostgresAPIRepository(cursor)

  @property
  def repo(self):
    return self._local.repo
