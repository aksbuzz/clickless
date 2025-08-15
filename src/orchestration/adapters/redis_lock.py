import structlog

from shared.loggin_config import setup_logging
from src.orchestration.domain.ports import LockPort

setup_logging()
log = structlog.get_logger()

class RedisLockService(LockPort):
  def __init__(self, redis_client):
    self.redis = redis_client
    self.locks = set()

  def acquire_lock(self, key: str, timeout: int):
    try:
      lock = self.redis.lock(key, timeout=timeout)
      acquired = lock.acquire(blocking=False)

      if acquired:
        self.locks.add(key)
        log.debug("Lock acquired", lock_key=key)
      else:
        log.debug("Failed to acquire logck", lock_key=key)

      return acquired
  
    except Exception as e:
      log.error("Lock acquisition failed", lock_key=key, exc_info=True)
      return False
  
  def release_lock(self, key: str):
    try:
      if key in self.locks:
        lock = self.redis.lock(key)
        lock.release()
        self.locks.discard(key)
        log.debug("Lock released", lock_key=key)
    except Exception as e:
      log.warning("Lock release failed", lock_key=key, exc_info=True)