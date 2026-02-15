import time
import structlog

from src.shared.logging_config import setup_logging
from src.shared.celery_app import app as celery_app
from src.relay.service import RelayService

setup_logging()
log = structlog.get_logger()

POLL_INTERVAL_SECONDS = 1.0


def main():
  service = RelayService(celery_app)

  log.info("Relay service started")

  while True:
    try:
      processed = service.relay_messages()
      if processed == 0:
        time.sleep(POLL_INTERVAL_SECONDS)
    except Exception:
      log.error("Relay error; retrying in 5 seconds.", exc_info=True)
      time.sleep(5)


if __name__ == '__main__':
  main()
