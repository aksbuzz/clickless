from src.shared.logging_config import log
from src.orchestration.domain.ports import LockPort

class PostgresLockService(LockPort):
  def __init__(self, cursor):
    self.cursor = cursor
  
  def acquire_lock(self, key, timeout):
    try:
      self.cursor.execute("SELECT pg_advisory_lock(%s);", (key,))
      log.debug("Lock acquired", lock_key=key)
      return True
    except Exception:
      log.error("Lock acquisition failed", lock_key=key, exc_info=True)
      return False
    
  def release_lock(self, key):
    try:
      self.cursor.execute("SELECT pg_advisory_unlock(%s);", (key,))
      log.debug("Lock released", lock_key=key)
    except Exception:
      log.warning("Lock release failed", lock_key=key, exc_info=True)