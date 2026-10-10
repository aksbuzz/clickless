# 0001. Record architecture decisions

- Status: Accepted
- Date: 2026-10-07

## Context

The platform has grown over roughly 20 commits into several cooperating processes (API, relay, engine, action workers, beat) backed by PostgreSQL, RabbitMQ and Redis. The `docs/*.md` files explain how the system works, but they do not record why choices were made, which alternatives were rejected, or which trade-offs were accepted knowingly. Some of those documents have also drifted from the code (see audit finding F-22).

## Decision

Keep a decision log in `docs/adr/`:

- One Markdown file per decision, named `NNNN-kebab-title.md`, numbered in order of recording.
- Each ADR has: Status, Date, Context, Decision, Alternatives considered, Consequences, and References.
- An accepted ADR is not rewritten to hide history. To change a decision, add a new ADR and mark the old one `Superseded by NNNN`. Factual corrections and added cross-references are fine.
- Statuses: `Proposed`, `Accepted`, `Accepted - under review` (in force but known to be unsatisfactory), `Superseded by NNNN`, `Rejected`.
- A pull request that changes one of these decisions adds or supersedes an ADR in the same PR.

ADRs 0002 to 0016 were written retrospectively on 2026-10-07 from the code, git history and `docs/*.md`. They describe the system as it is, not as it was intended to be.

## Alternatives considered

- Keep everything in `docs/architecture.md`: it describes the structure well, but mixing rationale into an overview makes both harder to maintain, and decisions get overwritten instead of superseded.
- Rely on commit messages and PR descriptions: they are not discoverable and the project's commit messages are terse.

## Consequences

- Small ongoing cost: one short file per significant decision.
- The `docs/*.md` files stay the explanatory overview. ADRs are the log of decisions.
- Retrospective "alternatives considered" sections reflect evident trade-offs, not a transcript of earlier discussion. Confirm with the original authors when it matters.

## References

- Michael Nygard, "Documenting Architecture Decisions"
- `docs/adr/README.md` (index)
