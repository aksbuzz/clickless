import logging
import sys
import structlog

def setup_logging():
  shared_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.add_log_level,
    structlog.stdlib.add_logger_name,
  ]

  structlog.configure(
    processors=[
      *shared_processors,
      structlog.stdlib.PositionalArgumentsFormatter(),
      structlog.processors.format_exc_info,
      structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True
  )

  formatter = structlog.stdlib.ProcessorFormatter(
    foreign_pre_chain=shared_processors,
    processor=structlog.processors.JSONRenderer(),
  )

  handler = logging.StreamHandler(sys.stdout)
  handler.setFormatter(formatter)

  root_logger = logging.getLogger()
  # Clear existing handlers to avoid duplicate logs
  if root_logger.hasHandlers():
      root_logger.handlers.clear()
  root_logger.addHandler(handler)
  root_logger.setLevel(logging.INFO)

  for _log in ["pika", "celery", "uvicorn", "aioredis"]:
    logging.getLogger(_log).setLevel(logging.WARNING)

  structlog.contextvars.clear_contextvars()

# Automatically configure logging when this module is imported
setup_logging()
log = structlog.get_logger()
