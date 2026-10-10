# 0010. In-process Python code step

- Status: Accepted - under review (security: F-02, must be revisited before any exposure)
- Date: 2026-10-07 (recorded retrospectively)

## Context

Users need small bespoke transformations (the seed `order_priority_workflow` computes a priority from a quantity) without writing a new connector. A code step is the cheapest way to give them that.

## Decision

The `python_execute` action (`src/worker/handlers/python_executor.py`) runs user code with `exec` inside the action worker process:

- The code runs in a daemon thread; the handler waits with `thread.join(timeout)`. Default timeout is 30 s, capped at 300 s.
- The namespace exposes `data` (the instance data, mutable) and a copy of `builtins` with `open`, `exec`, `eval`, `compile`, `__import__`, `exit` and `quit` removed.
- `__import__` is replaced by a function that only allows `math`, `json`, `re` and `datetime`.
- Whatever `data` holds afterwards is returned as the step result and merged into the instance.

The intent is a restricted sandbox, built from a blacklist of builtins plus an import allowlist.

## Alternatives considered

- No code step; offer only declarative transforms (`transform_data`, branch conditions).
- A restricted expression language (CEL, JSONata, `simpleeval`) for transforms and conditions.
- Run code in a separate OS process with resource limits, or in a container sandbox (gVisor, nsjail, Firecracker).
- A WebAssembly runtime (for example Pyodide under wasmtime).

## Consequences

Positive:

- Very low friction; no extra infrastructure.

Negative (F-02):

- This is not a security boundary. Restricting names in `builtins` and wrapping `__import__` does not isolate code that runs in the same interpreter. On 2026-10-07 a harmless probe run through the real handler confirmed that the import allowlist can be bypassed, so workflow authors should be treated as able to run arbitrary code as the worker user. Details are intentionally not recorded here.
- The worker process environment holds `DATABASE_URL`, `RABBITMQ_URL` and `REDIS_URL`, and the worker has network access to Postgres, RabbitMQ and Redis. Code running in the worker can therefore reach the platform's own datastores.
- Because the API has no authentication (ADR 0009, F-03), anyone who can reach it can create and run such a workflow.
- The timeout does not stop the work. A Python thread cannot be killed, so on timeout the handler reports failure while the code keeps consuming CPU in a daemon thread until the process restarts.
- `data` is mutated in place and the whole object is returned, so a code step can overwrite any key in the instance data.

Direction (to be decided in a superseding ADR): remove the step, replace it with an expression language, or move execution into an out-of-process sandbox with resource limits and no network or secrets. Until then it should be disabled by default and never exposed to untrusted authors.

## References

- `src/worker/handlers/python_executor.py`
- `src/shared/connectors/definitions/python.py`, `infrastructure/postgres/init.sql` (seed workflow uses it)
- Related: ADR 0008, ADR 0011
