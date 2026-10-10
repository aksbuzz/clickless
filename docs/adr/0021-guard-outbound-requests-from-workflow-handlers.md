# 0021. Guard outbound requests made by workflow handlers

- Status: Accepted
- Date: 2026-10-10

## Context

Workflow authors choose where handlers connect: the URL of `http_request` and `send_webhook`, the Slack `webhook_url`, and the PostgreSQL `connection_string`. The worker runs inside the Docker network, so those destinations could be the platform's own Postgres or API, other internal services, or a cloud metadata address such as `169.254.169.254`. `http_request` also stored the full response body in the instance data, which the API serves, making server-side request forgery a way to read internal services (audit F-06).

## Decision

Add `src/shared/net_guard.py` and call it from every handler that opens a connection on a user's behalf:

- **Public addresses only by default.** A URL must be `http` or `https` and have a host. The host is resolved, and every address it resolves to must be globally routable (`ipaddress.is_global`; IPv4-mapped IPv6 is unwrapped first). Loopback, private, link-local, carrier-grade NAT and other reserved ranges are refused. Short and decimal IP forms (`127.1`, `2130706433`) are caught because the resolver, not string matching, decides. Unresolvable hosts are refused (fail closed).
- **Operator overrides** through environment variables: `OUTBOUND_ALLOW_HOSTS` (comma-separated hosts or IPs that are always allowed) and `OUTBOUND_ALLOW_PRIVATE=true` (everything allowed, for development).
- **PostgreSQL handlers** parse the connection string (`host` and `hostaddr`, including comma-separated multi-host lists) and apply the same check. A string with no host, which would connect over a local socket, is refused.
- **Bounded responses.** `http_request` streams the body and fails once it exceeds `OUTBOUND_MAX_RESPONSE_BYTES` (default 1 MiB). `send_webhook` and Slack no longer read the body at all.
- Redirects are not followed, so a public server cannot bounce a request to an internal address.

A blocked request fails the step with a message that names the reason (for example "Blocked outbound request: 'x' resolves to a non-public address (10.0.0.5)"), and no connection is attempted. Tests start a real local HTTP server and assert it receives nothing when the request is blocked.

## Alternatives considered

- A network-level control (egress firewall, a proxy that enforces an allowlist, separate network for workers). Stronger and independent of application code, and worth adding in deployment; it does not replace a clear application-level refusal.
- An allowlist only (no outbound by default). Safest, but every new integration would need configuration before it works.
- Pinning the resolved IP for the actual connection to close the DNS-rebinding gap. More robust; needs a custom HTTP transport and was not done.

## Consequences

Positive:

- Closes the practical SSRF paths to the platform's own database and API, other internal services, and the cloud metadata service.
- Responses can no longer exhaust worker memory.
- The reason for a refusal is visible in the step's error.

Negative / follow-up:

- **Behaviour change.** Workflows that call internal services or private databases are refused until the operator allows the host in `OUTBOUND_ALLOW_HOSTS`. The default compose setup does not allow any.
- DNS rebinding is not covered: the name is resolved here and again by the client, so a hostile DNS server that changes its answer between the two lookups could pass the check. Mitigate with network egress rules.
- GitHub, Trello and the other connectors call fixed API hosts and are not guarded, though `owner`, `repo` and `card_id` values are still templated into URL paths.
- `getaddrinfo` blocks the worker thread, and an unresolvable name can take seconds.

## References

- `src/shared/net_guard.py`, `src/worker/handlers/action_handlers.py`, `slack.py`, `postgresql.py`
- `tests/unit/test_net_guard.py`, `tests/unit/test_outbound_handlers.py`
- `docs/audit-2026-10-07.md` (F-06), ADR 0011
