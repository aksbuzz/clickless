"""Encrypt every stored connection credential with the current SECRETS_KEY.

    docker compose run --rm api python -m src.api.encrypt_connections

Run it once after upgrading (it turns plaintext credentials into encrypted ones) and again after putting a new
key first in SECRETS_KEY (it re-encrypts everything with the new key, after which the old key can be dropped).
It is safe to repeat. Either every connection is updated or, if any stored value cannot be decrypted, none is.
Connections whose connector is no longer registered are left alone and listed.
"""
import json
from dataclasses import dataclass, field

import src.shared.connectors.definitions  # noqa: F401  (registers the connectors)
from src.shared import credentials
from src.shared.connectors.registry import registry
from src.shared.db import db_cursor


@dataclass
class Result:
    updated: int = 0
    skipped: list = field(default_factory=list)


def reencrypt_all(cur) -> Result:
    result = Result()
    cur.execute("SELECT id, connector_id, config FROM connections ORDER BY id FOR UPDATE")
    for row in cur.fetchall():
        connector = registry.get_connector(row["connector_id"])
        schema = connector.connection_schema if connector else {}
        if not schema:
            result.skipped.append(str(row["id"]))
            continue
        config = row["config"] or {}
        plain = {key: credentials.decrypt(value) if isinstance(value, str) else value for key, value in config.items()}
        fresh = credentials.protect(plain, schema)
        cur.execute("UPDATE connections SET config = %s WHERE id = %s", (json.dumps(fresh), row["id"]))
        result.updated += 1
    return result


def main() -> None:
    credentials.check_configured()
    with db_cursor() as cur:
        result = reencrypt_all(cur)
    print(f"Encrypted {result.updated} connection(s) with the current SECRETS_KEY.")
    for connection_id in result.skipped:
        print(f"Skipped {connection_id}: its connector is not registered, so its secret fields are unknown.")


if __name__ == "__main__":
    main()
