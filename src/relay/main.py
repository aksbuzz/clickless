import time
import structlog

from shared.loggin_config import setup_logging
from shared.db import get_db_connection
from shared.celery_app import app as celery_app

from src.relay.application.service import RelayService

from src.relay.adapters.postgres_repository import PostgresOutboxRepository
from src.relay.adapters.dict_router import DictTaskRouter
from src.relay.adapters.celery_publisher import CeleryTaskPublisher

setup_logging()
log = structlog.get_logger()

TASK_ROUTING = {
  'orchestration_queue': 'engine.orchestrate',
  'actions_queue': 'worker.execute_action'
}

def main():
  outbox_repo = PostgresOutboxRepository(get_db_connection)
  router = DictTaskRouter(TASK_ROUTING)
  publisher = CeleryTaskPublisher(celery_app)

  service = RelayService(outbox_repo, publisher, router)

  while True:
    try:
      service.keep_listening()
    except Exception:
      log.error("Relay crashed unexpectedly; restarting in 5 seconds.", exc_info=True)
      time.sleep(5)

if __name__ == '__main__':
  main()