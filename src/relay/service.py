from src.shared.logging_config import log
from src.shared.constants import ORCHESTRATION_QUEUE, ACTIONS_QUEUE
from src.shared.db import db_cursor


TASK_ROUTING = {
    ORCHESTRATION_QUEUE: "engine.orchestrate",
    ACTIONS_QUEUE: "worker.execute_action",
}


class RelayService:
    def __init__(self, celery_app, batch_size=100):
        self.celery_app = celery_app
        self.batch_size = batch_size

    def relay_messages(self) -> int:
        with db_cursor() as cur:
            cur.execute(
                "SELECT id, destination, payload, request_id "
                "FROM outbox "
                "WHERE processed_at IS NULL AND publish_at <= NOW() "
                "ORDER BY publish_at "
                "LIMIT %s "
                "FOR UPDATE SKIP LOCKED",
                (self.batch_size,)
            )
            messages = cur.fetchall()
            if not messages:
                return 0

            processed_ids = []
            for msg in messages:
                task_name = TASK_ROUTING.get(msg["destination"])
                if not task_name:
                    log.error("No task mapping for destination; skipping.", destination=msg["destination"], msg_id=str(msg["id"]))
                    continue

                try:
                    headers = {}
                    if msg.get("request_id"):
                        headers["request_id"] = msg["request_id"]

                    self.celery_app.send_task(
                        name=task_name,
                        args=[msg["payload"]],
                        queue=msg["destination"],
                        headers=headers
                    )
                    processed_ids.append(str(msg["id"]))
                except Exception as e:
                    log.error("Failed to send task; will retry later.", msg_id=str(msg["id"]), destination=msg["destination"], error=str(e))
                    break

            if processed_ids:
                cur.execute(
                    "UPDATE outbox SET processed_at = NOW() WHERE id = ANY(%s::uuid[])",
                    (processed_ids,)
                )
                log.info("Relayed messages.", count=len(processed_ids))

            return len(processed_ids)
