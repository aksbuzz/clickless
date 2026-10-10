# 0001. Record architecture decisions

- Status: Accepted
- Date: 2026-10-07

## Context

The platform runs as several cooperating pieces backed by PostgreSQL. The documents under `docs/` explain how it works, but they do not say why choices were made, which alternatives were rejected, or which trade-offs were accepted knowingly.

## Decision

Keep a decision log in `docs/adr/`:

- One Markdown file per decision, named `NNNN-kebab-title.md`, numbered in the order recorded. Numbers are never reused.
- Each ADR has: Status, Date, Context, Decision, Alternatives considered, Consequences, and References.
- **The log describes the code as it is.** An ADR is edited when the code it describes changes. When a decision is replaced and its code is removed, the old ADR is deleted, not kept as "superseded": the reasoning that still matters moves into the ADR that replaced it, and git history keeps the original. The index (`README.md`) lists the numbers that no longer exist.
- Statuses: `Proposed`, `Accepted`, `Accepted - under review` (in force but with known problems), `Rejected`.
- A pull request that changes one of these decisions edits or adds an ADR in the same PR.

## Alternatives considered

- Keep everything in `docs/architecture.md`: it describes the structure well, but rationale mixed into an overview gets overwritten and lost.
- Keep superseded ADRs as history: standard practice, but a log full of descriptions of deleted code misleads readers; git already keeps the history.
- Rely on commit messages and PR descriptions: not discoverable.

## Consequences

- A small ongoing cost: keeping the ADRs in step with the code.
- `docs/architecture.md`, `reliability.md`, `scalability.md` and `worker-and-scheduler.md` are the explanatory overview; the ADRs are the decision log.
- "Alternatives considered" in ADRs written after the fact (0004 to 0016) reflect evident trade-offs, not a record of earlier discussions.

## References

- Michael Nygard, "Documenting Architecture Decisions"
- `docs/adr/README.md` (index)
