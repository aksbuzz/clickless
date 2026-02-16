"""
Health check utilities for monitoring service dependencies.
"""
from typing import Dict, Any
from datetime import datetime
import time

from src.shared.redis_client import redis_client
from src.shared.celery_app import app as celery_app
from src.shared.logging_config import log


class HealthChecker:
    """Performs health checks on all system dependencies."""

    @staticmethod
    def check_postgres(cursor) -> Dict[str, Any]:
        """Check PostgreSQL connectivity and responsiveness."""
        try:
            start = time.time()
            cursor.execute("SELECT 1")
            latency_ms = round((time.time() - start) * 1000, 2)
            return {
                "status": "healthy",
                "latency_ms": latency_ms
            }
        except Exception as e:
            log.error("PostgreSQL health check failed", exc_info=True)
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    @staticmethod
    def check_redis() -> Dict[str, Any]:
        """Check Redis connectivity and responsiveness."""
        try:
            start = time.time()
            redis_client.ping()
            latency_ms = round((time.time() - start) * 1000, 2)

            # Get Redis info for additional metrics
            info = redis_client.info()
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human")
            }
        except Exception as e:
            log.error("Redis health check failed", exc_info=True)
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    @staticmethod
    def check_rabbitmq() -> Dict[str, Any]:
        """Check RabbitMQ connectivity via Celery broker."""
        try:
            start = time.time()
            # Try to connect to the broker
            with celery_app.connection_or_acquire() as conn:
                conn.connect()
            latency_ms = round((time.time() - start) * 1000, 2)
            return {
                "status": "healthy",
                "latency_ms": latency_ms
            }
        except Exception as e:
            log.error("RabbitMQ health check failed", exc_info=True)
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    @staticmethod
    def check_celery_workers() -> Dict[str, Any]:
        """Check Celery worker availability."""
        try:
            # Get active workers
            inspect = celery_app.control.inspect(timeout=2.0)
            stats = inspect.stats()

            if not stats:
                return {
                    "status": "unhealthy",
                    "error": "No workers available",
                    "workers": []
                }

            workers = []
            for worker_name, worker_stats in stats.items():
                workers.append({
                    "name": worker_name,
                    "pool": worker_stats.get("pool", {}).get("implementation"),
                    "max_concurrency": worker_stats.get("pool", {}).get("max-concurrency")
                })

            return {
                "status": "healthy",
                "worker_count": len(workers),
                "workers": workers
            }
        except Exception as e:
            log.error("Celery worker health check failed", exc_info=True)
            return {
                "status": "unhealthy",
                "error": str(e),
                "workers": []
            }

    @classmethod
    def comprehensive_check(cls, db_cursor) -> Dict[str, Any]:
        """
        Perform comprehensive health check of all dependencies.

        Returns a detailed health status report including:
        - Overall status
        - Individual component statuses
        - Timestamp
        """
        checks = {
            "postgres": cls.check_postgres(db_cursor),
            "redis": cls.check_redis(),
            "rabbitmq": cls.check_rabbitmq(),
            "celery_workers": cls.check_celery_workers()
        }

        # Determine overall status
        all_healthy = all(
            check.get("status") == "healthy"
            for check in checks.values()
        )

        return {
            "status": "healthy" if all_healthy else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": checks
        }
