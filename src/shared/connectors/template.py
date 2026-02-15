import re
from typing import Any, Dict

_TEMPLATE_PATTERN = re.compile(r"\{\{(\s*[\w.]+\s*)\}\}")


def resolve_field(data: dict, field_path: str) -> Any:
    """Resolve a dot-separated field path like 'invoice.amount'."""
    parts = field_path.strip().split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def resolve_template(value: str, data: dict) -> str:
    """Replace all {{field.path}} placeholders in a string with values from data."""
    def replacer(match: re.Match) -> str:
        field_path = match.group(1).strip()
        resolved = resolve_field(data, field_path)
        if resolved is None:
            return match.group(0)
        return str(resolved)

    return _TEMPLATE_PATTERN.sub(replacer, value)


def resolve_config(config: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-resolve all string values in a config dict against workflow data."""
    resolved = {}
    for key, value in config.items():
        if isinstance(value, str):
            resolved[key] = resolve_template(value, data)
        elif isinstance(value, dict):
            resolved[key] = resolve_config(value, data)
        elif isinstance(value, list):
            resolved[key] = [
                resolve_template(item, data) if isinstance(item, str) else item
                for item in value
            ]
        else:
            resolved[key] = value
    return resolved
