"""The in-process Python code step was removed (docs/adr/0019): it could not be sandboxed."""
import json
import pathlib
import re

import src.shared.connectors.definitions  # noqa: F401 - registers the connectors
from src.shared.connectors.registry import registry
from src.worker.registry import get_registry

INIT_SQL = pathlib.Path(__file__).resolve().parents[2] / "infrastructure" / "postgres" / "init.sql"


def seed_definition() -> dict:
    """The JSON definition of the seeded workflow, extracted from init.sql."""
    sql = INIT_SQL.read_text()
    match = re.search(r"VALUES \(wf_id, 1, '(.*?)'\);", sql, re.S)
    assert match, "seed workflow INSERT not found in init.sql"
    return json.loads(match.group(1).replace("''", "'"))


def test_python_connector_is_not_offered():
    assert registry.get_connector("python") is None
    assert registry.get_action("python_execute") is None


def test_python_action_has_no_handler():
    assert "python_execute" not in get_registry()


def test_seed_workflow_only_uses_registered_actions():
    assert registry.validate_definition(seed_definition()) == []


def test_seed_workflow_still_branches_on_order_quantity():
    steps = seed_definition()["steps"]
    branches = [s for s in steps.values() if s.get("type") == "branch"]
    assert len(branches) == 1
    assert branches[0]["condition"] == {"field": "order.quantity", "operator": "gte", "value": 100}
