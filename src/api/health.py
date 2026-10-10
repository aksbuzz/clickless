import os
import time
from datetime import datetime, timezone
from typing import Any, Dict

from src.engine import runtime
from src.shared.logging_config import log

DEFAULT_MAX_JOB_AGE_SECONDS = 30.0


def _max_job_age() -> float:
    try:
        return float(os.getenv("HEALTH_MAX_JOB_AGE_SECONDS", DEFAULT_MAX_JOB_AGE_SECONDS))
    except ValueError:
        return DEFAULT_MAX_JOB_AGE_SECONDS


class HealthChecker:
    """Two things can be wrong: the database is unreachable, or due jobs are not being picked up (no worker)."""

    @staticmethod
    def check_postgres(cursor) -> Dict[str, Any]:
        try:
            start = time.time()
            cursor.execute("SELECT 1")
            latency_ms = round((time.time() - start) * 1000, 2)
            return {"status": "healthy", "latency_ms": latency_ms}
        except Exception as e:
            log.error("PostgreSQL health check failed", exc_info=True)
            return {"status": "unhealthy", "error": str(e)}

    @staticmethod
    def check_queue(cursor) -> Dict[str, Any]:
        try:
            stats = runtime.queue_stats(cursor)
        except Exception as e:
            log.error("Job queue health check failed", exc_info=True)
            return {"status": "unhealthy", "error": str(e)}
        oldest = stats["oldest_due_seconds"]
        if oldest is not None and oldest > _max_job_age():
            return {
                "status": "unhealthy", **stats,
                "error": f"jobs have been waiting {oldest} s to be picked up; is a worker running?",
            }
        return {"status": "healthy", **stats}

    @classmethod
    def comprehensive_check(cls, cursor) -> Dict[str, Any]:
        checks = {
            "postgres": cls.check_postgres(cursor),
            "queue": cls.check_queue(cursor),
        }
        all_healthy = all(c.get("status") == "healthy" for c in checks.values())
        return {
            "status": "healthy" if all_healthy else "degraded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
        }
