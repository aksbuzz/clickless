# 0019. Remove the in-process Python code step

- Status: Accepted
- Date: 2026-10-10
- Replaced an earlier decision to run user code in the worker (its ADR was deleted with the code)

## Context

Workflows had a `python_execute` action that ran user code with `exec` inside the action worker, behind a builtins blacklist and an import allowlist. The audit (F-02) showed this is not a security boundary: running the real handler with a harmless probe confirmed the allowlist can be bypassed, so anyone who can create a workflow can run arbitrary code in a process that holds the database credentials and every stored connection credential. The timeout also cannot stop runaway code. Until the API had authentication (ADR 0020) that meant unauthenticated remote code execution.

Options were put to the project owner on 2026-10-10: disable it behind a flag, remove it, or keep it for now. The decision was to remove it.

## Decision

Delete the step entirely:

- `src/worker/handlers/python_executor.py` and `src/shared/connectors/definitions/python.py` are removed, along with their registrations in `src/worker/registry.py` and `src/shared/connectors/definitions/__init__.py`.
- The seeded `order_priority_workflow` no longer computes the priority in code. It branches directly on `order.quantity >= 100` and sets `priority`, `expedited` and `shipping_days` with `transform_data`. The README example is updated to match.
- `tests/unit/test_removed_python_step.py` guards the removal: the connector and handler are absent, the seed definition validates against the registered actions, and the seed still branches on the order quantity.

## Alternatives considered

- Keep it behind an off-by-default flag. Smaller change, but leaves a code path that is dangerous the moment someone turns it on.
- Replace it with a restricted expression language (CEL, JSONata, `simpleeval`) for computed values and conditions. Likely worth doing later; it is a feature, not a fix.
- Move execution into an out-of-process sandbox (container, gVisor, nsjail, WebAssembly) with no secrets and no network. Strongest isolation for arbitrary code, and the largest build.

## Consequences

Positive:

- Closes the arbitrary code execution path in the worker (F-02).
- One less place where workflow authors can reach the worker's credentials.

Negative / follow-up:

- Workflows can no longer compute values with code. The remaining tools are `branch` conditions (`eq neq gt gte lt lte contains exists`) and `transform_data` (set and remove fields). If computed values are needed, add an expression language in a new ADR.
- **Existing databases.** `init.sql` only runs on an empty volume, so a database created earlier still has the old seed workflow, and any user workflow may use `python_execute`. New saves are rejected by `validate_definition` (unknown connector or action id), but stored versions are not touched and will fail at run time: the step is recorded as failed with "no handler registered for action 'python_execute'" and the instance ends as `failed`. Find them with:

  ```sql
  SELECT w.name, v.version
  FROM workflow_versions v JOIN workflows w ON w.id = v.workflow_id
  WHERE v.is_active AND v.definition::text LIKE '%python_execute%';
  ```

  Then edit them in the UI (or create a new version), or delete the old seed workflow.
- The other handler risks (SQL built from templates, outbound requests to internal hosts) are separate findings (F-05, F-06).

## References

- `docs/audit-2026-10-07.md` (F-02)
- ADR 0008, ADR 0020
