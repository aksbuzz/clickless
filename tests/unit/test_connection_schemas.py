"""Every credential a connector asks for must be flagged write-only, or it would be stored and returned as plain text."""
import pytest

import src.shared.connectors.definitions  # noqa: F401  (registers the connectors)
from src.shared.connectors.registry import registry
from src.shared.credentials import secret_fields

CREDENTIAL_FIELDS = {
    "github": {"token"},
    "slack": {"webhook_url"},
    "trello": {"api_key", "api_token"},
    "postgresql": {"connection_string"},
}


@pytest.mark.parametrize("connector_id,fields", sorted(CREDENTIAL_FIELDS.items()))
def test_credential_fields_are_marked_write_only(connector_id, fields):
    connector = registry.get_connector(connector_id)
    assert secret_fields(connector.connection_schema) == fields


def test_every_connector_that_takes_a_connection_is_covered_here():
    with_connections = {c.id for c in registry.list_connectors() if c.connection_schema}
    assert with_connections == set(CREDENTIAL_FIELDS), "a new connector needs its secret fields listed in this test"
