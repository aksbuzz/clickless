"""Deleting finished runs after a retention period.

Every run leaves an instance row with its data and one row per step attempt. Finished jobs are deleted by the
engine, but these stay, so without housekeeping the tables only grow. ``Housekeeper`` runs inside the worker
process: it deletes runs that finished (completed, failed or cancelled) more than ``RETENTION_DAYS`` ago, in
small batches, each its own short transaction. Step attempts and dead jobs go with their run (ON DELETE CASCADE).

Runs that have not finished are never touched, however old. Rows that another transaction holds (a cancel, a
worker finishing a step) are skipped, not waited for, so several workers can run this at once.
"""
import threading
import time

from src.shared.db import db_cursor
from src.shared.logging_config import log
from src.shared.metrics import retention_deleted_total

DEFAULT_RETENTION_DAYS = 30
FINISHED = ("completed", "failed", "cancelled")

# Uses idx_instances_finished (a partial index on updated_at for finished runs).
PURGE_SQL = (
    "DELETE FROM workflow_instances WHERE id IN ("
    "  SELECT id FROM workflow_instances"
    "  WHERE status = ANY(%s) AND updated_at < now() - make_interval(days => %s)"
    "  ORDER BY updated_at LIMIT %s"
    "  FOR UPDATE SKIP LOCKED)"
)


def purge_finished(cur, days: int, batch_size: int = 500) -> int:
    """Delete up to ``batch_size`` runs that finished more than ``days`` days ago, oldest first. Returns how many."""
    if days <= 0:
        raise ValueError(f"days must be greater than 0, got {days}")
    cur.execute(PURGE_SQL, (list(FINISHED), days, batch_size))
    return cur.rowcount


class Housekeeper:
    def __init__(self, days: int, interval: float = 3600.0, initial_delay: float = 60.0,
                 batch_size: int = 500, pause: float = 0.05):
        self.days, self.interval, self.initial_delay = days, interval, initial_delay
        self.batch_size, self.pause = batch_size, pause

    def run_once(self) -> int:
        """Delete everything that is due, one batch at a time. Returns the total."""
        total = 0
        while True:
            with db_cursor() as cur:
                deleted = purge_finished(cur, self.days, self.batch_size)
            total += deleted
            if deleted:
                retention_deleted_total.inc(deleted)
            if deleted < self.batch_size:
                return total
            time.sleep(self.pause)     # let the database breathe between batches

    def run(self, stop: threading.Event) -> None:
        log.info("Retention started", days=self.days, interval_seconds=self.interval)
        wait = self.initial_delay
        while not stop.wait(wait):
            try:
                deleted = self.run_once()
                if deleted:
                    log.info("Retention deleted finished runs", deleted=deleted, older_than_days=self.days)
            except Exception as exc:       # never take the worker down; try again next time
                log.error("Retention pass failed", error=str(exc))
            wait = self.interval
