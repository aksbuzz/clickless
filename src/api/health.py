from typing import Dict, Any
from datetime import datetime
import time

from src.shared.redis_client import redis_client
from src.shared.celery_app import app as celery_app
from src.shared.logging_config import log


class HealthChecker:

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
    def check_redis() -> Dict[str, Any]:
        try:
            start = time.time()
            redis_client.ping()
            latency_ms = round((time.time() - start) * 1000, 2)
            info = redis_client.info()
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human"),
            }
        except Exception as e:
            log.error("Redis health check failed", exc_info=True)
            return {"status": "unhealthy", "error": str(e)}

    @staticmethod
    def check_rabbitmq() -> Dict[str, Any]:
        try:
            start = time.time()
            with celery_app.connection_or_acquire() as conn:
                conn.connect()
            latency_ms = round((time.time() - start) * 1000, 2)
            return {"status": "healthy", "latency_ms": latency_ms}
        except Exception as e:
            log.error("RabbitMQ health check failed", exc_info=True)
            return {"status": "unhealthy", "error": str(e)}

    @staticmethod
    def check_celery_workers() -> Dict[str, Any]:
        try:
            inspect = celery_app.control.inspect(timeout=2.0)
            stats = inspect.stats()
            if not stats:
                return {"status": "unhealthy", "error": "No workers available", "workers": []}
            workers = [
                {
                    "name": name,
                    "pool": s.get("pool", {}).get("implementation"),
                    "max_concurrency": s.get("pool", {}).get("max-concurrency"),
                }
                for name, s in stats.items()
            ]
            return {"status": "healthy", "worker_count": len(workers), "workers": workers}
        except Exception as e:
            log.error("Celery worker health check failed", exc_info=True)
            return {"status": "unhealthy", "error": str(e), "workers": []}

    @classmethod
    def comprehensive_check(cls, db_cursor) -> Dict[str, Any]:
        checks = {
            "postgres": cls.check_postgres(db_cursor),
            "redis": cls.check_redis(),
            "rabbitmq": cls.check_rabbitmq(),
            "celery_workers": cls.check_celery_workers(),
        }
        all_healthy = all(c.get("status") == "healthy" for c in checks.values())
        return {
            "status": "healthy" if all_healthy else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": checks,
        }
