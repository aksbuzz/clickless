from src.shared.logging_config import log

from src.orchestration.domain.ports import LockPort


class RedisLockService(LockPort):
  def __init__(self, redis_client):
    self.redis = redis_client
    self.locks = {}

  def acquire_lock(self, key: str, timeout: int):
    try:
      lock = self.redis.lock(key, timeout=timeout)
      acquired = lock.acquire(blocking=False)

      if acquired:
        self.locks[key] = lock
        log.debug("Lock acquired", lock_key=key)
      else:
        log.debug("Failed to acquire lock", lock_key=key)

      return acquired
    except Exception:
      log.error("Lock acquisition failed", lock_key=key, exc_info=True)
      return False

  def release_lock(self, key: str):
    try:
      lock = self.locks.pop(key, None)
      if lock:
        lock.release()
        log.debug("Lock released", lock_key=key)
      else:
        log.warning("No lock to release", lock_key=key)
    except Exception:
      log.warning("Lock release failed", lock_key=key, exc_info=True)
