import time
from typing import Optional

from src.shared.logging_config import log

from src.relay.domain.ports import UnitOfWorkPort, TaskPublisherPort, TaskRouterPort


class RelayService:
  def __init__(
    self,
    uow: UnitOfWorkPort,
    publisher: TaskPublisherPort,
    router: TaskRouterPort,
    poll_interval_seconds: float = 1.0,
    batch_size: int = 100,
  ):
    self.uow = uow
    self.publisher = publisher
    self.router = router
    self.poll_interval_seconds = poll_interval_seconds
    self.batch_size = batch_size

  def keep_listening(self):
    log.info("Relay service will begin listening")

    while True:
      processed = self.relay_messages()
      if processed == 0:
        time.sleep(self.poll_interval_seconds)

  
  def relay_messages(self) -> int:
    with self.uow:
      messages = self.uow.outbox.fetch_due_messages(self.batch_size)
      if not messages:
        return 0
      
      processed_ids = []
      for m in messages:
        task_name: Optional[str] = self.router.resolve_task_name(m.destination)
        if not task_name:
          log.error(
            "No task mapping for destination; skipping message.",
            destination=m.destination, msg_id=m.id
          )
          continue

        try:
          self.publisher.publish(task_name=task_name, queue=m.destination, payload=m.payload)
          processed_ids.append(m.id)
        except Exception as send_err:
          log.error(
            "Failed to send task; will retry later.",
            msg_id=m.id, destination=m.destination, error=str(send_err)
          )
          break

      if processed_ids:
        self.uow.outbox.mark_processed(processed_ids)
        log.info("Relayed messages.", count=len(processed_ids))

      return len(processed_ids)
