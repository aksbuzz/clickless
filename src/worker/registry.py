_HANDLERS: dict[str, type] = {}


def action(name: str):
    """Decorator to auto-register an action handler."""
    def decorator(cls):
        _HANDLERS[name] = cls
        return cls
    return decorator


def get_registry() -> dict:
    """Import all handler modules (triggering registration) and return instantiated handlers."""
    import src.worker.action_handlers.action_handlers  # noqa: F401
    import src.worker.action_handlers.slack             # noqa: F401
    import src.worker.action_handlers.github            # noqa: F401
    import src.worker.action_handlers.trello            # noqa: F401
    import src.worker.action_handlers.postgresql        # noqa: F401
    import src.worker.action_handlers.python_executor   # noqa: F401
    return {name: cls() for name, cls in _HANDLERS.items()}
