import time
import structlog

from src.shared.logging_config import setup_logging
from src.shared.db import get_db_connection
from src.shared.celery_app import app as celery_app

from src.relay.application.service import RelayService

from src.relay.adapters.postgres_unit_of_work import PostgresUnitOfWork
from src.relay.adapters.dict_router import DictTaskRouter
from src.relay.adapters.celery_publisher import CeleryTaskPublisher

setup_logging()
log = structlog.get_logger()

TASK_ROUTING = {
  'orchestration_queue': 'engine.orchestrate',
  'actions_queue': 'worker.execute_action'
}

def main():
  unit_of_work = PostgresUnitOfWork(get_db_connection())
  router = DictTaskRouter(TASK_ROUTING)
  publisher = CeleryTaskPublisher(celery_app)

  service = RelayService(unit_of_work, publisher, router)

  while True:
    try:
      service.keep_listening()
    except Exception:
      log.error("Relay crashed unexpectedly; restarting in 5 seconds.", exc_info=True)
      time.sleep(5)

if __name__ == '__main__':
  main()