"""Celery must not depend on a hardcoded, unauthenticated Redis result backend."""
from src.shared.celery_app import app


def test_task_results_are_not_stored():
    # No task result is ever read, and a hardcoded redis://redis:6379/1 breaks as soon as Redis has a password.
    assert app.conf.task_ignore_result is True


def test_no_result_backend_is_hardcoded():
    assert not str(app.conf.result_backend or "").startswith("redis://redis")
