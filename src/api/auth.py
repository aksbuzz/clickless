"""Shared API key authentication.

Every route requires `Authorization: Bearer <API_KEY>` unless it is explicitly public (the readiness
probe and the provider webhooks, which verify their own signatures). The check fails closed: with no key
configured, protected routes answer 503 and the API refuses to start.
"""
import hmac
import os

from fastapi import HTTPException, Request

MIN_KEY_LENGTH = 16


def _configured_key() -> str:
    return os.getenv("API_KEY", "").strip()


def validate_auth_config() -> None:
    if len(_configured_key()) < MIN_KEY_LENGTH:
        raise RuntimeError(
            f"API_KEY must be set to a secret of at least {MIN_KEY_LENGTH} characters "
            "(generate one with: openssl rand -hex 32)"
        )


def require_api_key(request: Request) -> None:
    expected = _configured_key()
    if not expected:
        raise HTTPException(status_code=503, detail="API key is not configured")
    scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(supplied.strip().encode(), expected.encode()):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
