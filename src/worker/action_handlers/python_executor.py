import threading
from typing import Any, Dict

from src.shared.logging_config import log
from src.worker.domain.models import ActionStatus
from src.worker.domain.ports import ActionHandlerPort, ActionResult

ALLOWED_MODULES = {"math", "json", "re", "datetime"}
MAX_TIMEOUT = 300
DEFAULT_TIMEOUT = 30


def _make_safe_import(allowed):
    """Create a restricted __import__ that only allows whitelisted modules."""
    def safe_import(name, *args, **kwargs):
        if name not in allowed:
            raise ImportError(f"Import of '{name}' is not allowed. Allowed: {', '.join(sorted(allowed))}")
        return __builtins__["__import__"](name, *args, **kwargs) if isinstance(__builtins__, dict) else __import__(name, *args, **kwargs)
    return safe_import


def _make_restricted_builtins():
    """Build a builtins dict with dangerous functions removed."""
    import builtins
    safe = dict(vars(builtins))
    for name in ("open", "exec", "eval", "compile", "__import__", "exit", "quit"):
        safe.pop(name, None)
    safe["__import__"] = _make_safe_import(ALLOWED_MODULES)
    return safe


class PythonExecuteHandler(ActionHandlerPort):
    def execute(self, instance_id, data, config=None, **kwargs):
        config = config or {}
        code = config.get("code", "")
        timeout = min(config.get("timeout_seconds", DEFAULT_TIMEOUT), MAX_TIMEOUT)

        if not code:
            return ActionResult(ActionStatus.FAILURE, data, error_message="Missing 'code' in config")

        log.info("Executing Python code", instance_id=instance_id, timeout=timeout)

        namespace: Dict[str, Any] = {
            "__builtins__": _make_restricted_builtins(),
            "data": data,
        }
        error_holder = [None]

        def run_code():
            try:
                exec(code, namespace)  # noqa: S102
            except Exception as e:
                error_holder[0] = e

        thread = threading.Thread(target=run_code, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            return ActionResult(ActionStatus.FAILURE, data, error_message=f"Code execution timed out after {timeout}s")

        if error_holder[0] is not None:
            return ActionResult(ActionStatus.FAILURE, data, error_message=f"Code execution error: {error_holder[0]}")

        # The code may have mutated `data` in-place or reassigned `namespace['data']`
        result_data = namespace.get("data", data)
        log.info("Python code executed", instance_id=instance_id)
        return ActionResult(ActionStatus.SUCCESS, result_data)
