"""Guard for outbound connections made on behalf of workflow authors.

Workflow configs choose URLs and database hosts. From inside the Docker network those could point at the
broker's admin port, Redis, Postgres or a cloud metadata address, so by default only public addresses are
allowed. Operators can open specific destinations with environment variables:

    OUTBOUND_ALLOW_HOSTS=db.internal,10.0.0.7    comma-separated hosts or IPs that are always allowed
    OUTBOUND_ALLOW_PRIVATE=true                  allow every destination (development only)
    OUTBOUND_MAX_RESPONSE_BYTES=1048576          cap on a response body a handler will read

Limits: a hostname is resolved here and again by the HTTP client, so a DNS answer that changes in between
(DNS rebinding) is not covered. Redirects are not followed by the handlers, so a public server cannot bounce
a request to an internal address.
"""
import ipaddress
import os
import socket
from urllib.parse import urlsplit

DEFAULT_MAX_RESPONSE_BYTES = 1024 * 1024


class OutboundBlocked(Exception):
    """The destination is not allowed."""


class ResponseTooLarge(Exception):
    """A response body exceeded the configured limit."""


def _allow_private() -> bool:
    return os.getenv("OUTBOUND_ALLOW_PRIVATE", "").strip().lower() in ("1", "true", "yes")


def _allowed_hosts() -> set:
    return {h.strip().lower() for h in os.getenv("OUTBOUND_ALLOW_HOSTS", "").split(",") if h.strip()}


def max_response_bytes() -> int:
    try:
        return int(os.getenv("OUTBOUND_MAX_RESPONSE_BYTES", DEFAULT_MAX_RESPONSE_BYTES))
    except ValueError:
        return DEFAULT_MAX_RESPONSE_BYTES


def check_host(host, port=None) -> None:
    """Raise OutboundBlocked unless every address `host` resolves to is public (or the host is allowed)."""
    if not host:
        raise OutboundBlocked("no host given")
    if _allow_private() or host.lower() in _allowed_hosts():
        return
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as exc:
        raise OutboundBlocked(f"cannot resolve host '{host}'") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if address.version == 6 and address.ipv4_mapped:
            address = address.ipv4_mapped
        if not address.is_global:
            raise OutboundBlocked(f"'{host}' resolves to a non-public address ({address}); see OUTBOUND_ALLOW_HOSTS")


def check_url(url) -> None:
    """Raise OutboundBlocked unless `url` is an http(s) URL to an allowed destination."""
    try:
        parts = urlsplit(url or "")
        port = parts.port
    except ValueError as exc:
        raise OutboundBlocked("invalid URL") from exc
    if parts.scheme not in ("http", "https"):
        raise OutboundBlocked("only http and https URLs are allowed")
    check_host(parts.hostname, port)


def read_limited(response) -> bytes:
    """Read a streamed httpx response body, refusing anything over the configured limit."""
    limit = max_response_bytes()
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise ResponseTooLarge(f"response is larger than {limit} bytes")
    chunks, total = [], 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > limit:
            raise ResponseTooLarge(f"response is larger than {limit} bytes")
        chunks.append(chunk)
    return b"".join(chunks)
