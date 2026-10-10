"""Protection of connection credentials.

A connector marks its secret fields with ``"writeOnly": true`` in ``connection_schema``. Those values are

* encrypted before they are stored (``protect``), as ``enc:v1:<Fernet token>``,
* decrypted only where a step is about to run (``reveal``), and
* never returned by the API (``redact`` keeps the non-secret fields and names the secrets that are set).

The key comes from ``SECRETS_KEY``: one Fernet key, or several separated by commas. The first key encrypts;
all of them decrypt, so a key can be rotated by putting the new one first and re-encrypting (see
``python -m src.api.encrypt_connections``). Make a key with::

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

A stored value without the ``enc:v1:`` tag is treated as legacy plaintext and read as it is, so databases
created before encryption existed keep working until they are re-encrypted.
"""
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

PREFIX = "enc:v1:"
ENV_VAR = "SECRETS_KEY"


class SecretsKeyError(RuntimeError):
    """SECRETS_KEY is missing or not a valid Fernet key."""


class SecretDecryptionError(RuntimeError):
    """A stored credential could not be decrypted: wrong key, or the value was altered."""


@lru_cache(maxsize=8)
def _build(raw: str) -> MultiFernet:
    keys = [part.strip() for part in raw.split(",") if part.strip()]
    if not keys:
        raise SecretsKeyError(f"{ENV_VAR} is empty")
    try:
        return MultiFernet([Fernet(key.encode()) for key in keys])
    except (ValueError, TypeError) as exc:
        raise SecretsKeyError(
            f"{ENV_VAR} must be one or more comma-separated Fernet keys (url-safe base64 of 32 bytes); "
            "make one with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        ) from exc


def _fernet() -> MultiFernet:
    raw = os.environ.get(ENV_VAR, "").strip()
    if not raw:
        raise SecretsKeyError(
            f"{ENV_VAR} is not set. Connection credentials are encrypted with it; "
            "run scripts/init-env.sh to create one."
        )
    return _build(raw)


def check_configured() -> None:
    """Raise SecretsKeyError unless a usable key is configured. Call at start-up."""
    _fernet()


def is_encrypted(value) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt(value: str) -> str:
    return PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """Decrypt a stored value; legacy plaintext is returned as it is."""
    if not is_encrypted(value):
        return value
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise SecretDecryptionError(
            f"could not decrypt a stored credential: {ENV_VAR} does not match the key it was encrypted with"
        ) from exc


def secret_fields(schema: dict) -> set:
    properties = (schema or {}).get("properties", {})
    return {name for name, spec in properties.items() if spec.get("writeOnly")}


def protect(config: dict, schema: dict) -> dict:
    """Return a copy of ``config`` with every non-empty secret value encrypted."""
    secrets = secret_fields(schema)
    return {
        key: encrypt(value) if key in secrets and isinstance(value, str) and value and not is_encrypted(value) else value
        for key, value in config.items()
    }


def reveal(config: dict) -> dict:
    """Return a copy of ``config`` with every encrypted value decrypted."""
    return {key: decrypt(value) if isinstance(value, str) else value for key, value in config.items()}


def redact(config: dict, schema: dict):
    """Return ``(config without its secret fields, sorted names of the secret fields that hold a value)``."""
    secrets = secret_fields(schema)
    public = {key: value for key, value in config.items() if key not in secrets}
    names = sorted(key for key in secrets if config.get(key))
    return public, names


def stored_secrets(stored: dict, schema: dict) -> set:
    """Names of the secret fields that already hold a value in a stored config."""
    return {name for name in secret_fields(schema) if stored.get(name)}


def validate_config(config, schema: dict, keep=()) -> list:
    """Problems with a connection config, as messages for the user. ``keep`` names secrets already stored."""
    if not isinstance(config, dict):
        return ["config must be an object"]
    properties = (schema or {}).get("properties", {})
    problems = []
    for key in config:
        if key not in properties:
            problems.append(f"Unknown field '{key}'")
    for key, spec in properties.items():
        title = spec.get("title", key)
        value = config.get(key)
        if value is not None and spec.get("type") == "string" and not isinstance(value, str):
            problems.append(f"{title} must be text")
    for key in (schema or {}).get("required", []):
        value = config.get(key)
        blank = value is None or (isinstance(value, str) and not value.strip())
        if blank and key not in keep:
            problems.append(f"{properties.get(key, {}).get('title', key)} is required")
    return problems


def merge_update(new_config: dict, stored: dict, schema: dict) -> dict:
    """The config to store after an edit.

    Secrets are write-only, so the edit form never has their values: a secret that is left out or blank keeps
    the stored value, and a non-blank one replaces it. Every other field comes from ``new_config`` alone.
    """
    secrets = secret_fields(schema)
    merged = {key: value for key, value in new_config.items() if key not in secrets}
    for name in secrets:
        value = new_config.get(name)
        if isinstance(value, str) and value.strip():
            merged[name] = value
        elif stored.get(name):
            merged[name] = stored[name]
    return merged
