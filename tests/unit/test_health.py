"""The health check reports Postgres and whether due jobs are being picked up."""
import pytest

from src.api.health import HealthChecker


class ScriptedCursor:
    """Returns queued answers to fetchone(); raises on execute when told to."""

    def __init__(self, answers=(), fail=None):
        self.answers = list(answers)
        self.fail = fail

    def execute(self, *args):
        if self.fail:
            raise self.fail

    def fetchone(self):
        return self.answers.pop(0)


def queue_cursor(due=0, running=0, oldest=None, dead=0):
    return ScriptedCursor([{"due": due, "running": running, "oldest_due_seconds": oldest}, {"dead": dead}])


def test_an_empty_queue_is_healthy():
    result = HealthChecker.check_queue(queue_cursor())
    assert result["status"] == "healthy"
    assert result["due"] == 0 and result["oldest_due_seconds"] is None


def test_jobs_that_were_picked_up_promptly_are_healthy():
    result = HealthChecker.check_queue(queue_cursor(due=4, running=2, oldest=3.2))
    assert result["status"] == "healthy"
    assert result["running"] == 2


def test_jobs_waiting_too_long_mean_no_worker_is_taking_them():
    result = HealthChecker.check_queue(queue_cursor(due=9, oldest=120.0))
    assert result["status"] == "unhealthy"
    assert "worker" in result["error"].lower()


def test_dead_jobs_are_reported_but_do_not_fail_the_check():
    result = HealthChecker.check_queue(queue_cursor(dead=3))
    assert result["status"] == "healthy" and result["dead"] == 3


def test_the_age_limit_can_be_set(monkeypatch):
    monkeypatch.setenv("HEALTH_MAX_JOB_AGE_SECONDS", "5")
    assert HealthChecker.check_queue(queue_cursor(due=1, oldest=10.0))["status"] == "unhealthy"


def test_a_database_failure_is_reported_not_raised():
    assert HealthChecker.check_postgres(ScriptedCursor(fail=RuntimeError("down")))["status"] == "unhealthy"
    assert HealthChecker.check_queue(ScriptedCursor(fail=RuntimeError("down")))["status"] == "unhealthy"


def test_postgres_check_reports_latency():
    class Cursor(ScriptedCursor):
        pass
    result = HealthChecker.check_postgres(Cursor())
    assert result["status"] == "healthy" and result["latency_ms"] >= 0


def test_overall_status_is_degraded_when_any_check_fails():
    cursor = queue_cursor(due=5, oldest=300.0)
    result = HealthChecker.comprehensive_check(cursor)
    assert result["status"] == "degraded"
    assert result["checks"]["postgres"]["status"] == "healthy"
    assert result["checks"]["queue"]["status"] == "unhealthy"


def test_overall_status_is_healthy_when_everything_is():
    result = HealthChecker.comprehensive_check(queue_cursor(due=1, oldest=1.0))
    assert result["status"] == "healthy"


def test_only_the_components_that_exist_are_checked():
    result = HealthChecker.comprehensive_check(queue_cursor())
    assert set(result["checks"]) == {"postgres", "queue"}
