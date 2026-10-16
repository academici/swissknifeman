# ADR 0021: Durable architecture documentation and decision records in the repository

## Status

Accepted

## Context

Plans are archived after they close, but architecture and decisions must remain readable.

## Decision

The repository keeps `docs/architecture/ecosystem.md` (the living architecture) and numbered decision records in
`docs/architecture/decisions/`. Records state context, alternatives, consequences and supersession. Each stage
updates what it touches. Diagrams are Mermaid. Structurizr and C4 DSL are rejected: a separate tool only for
diagrams.

## Alternatives considered

- Keep decisions only in working plans: rejected, they are archived.

## Consequences

- Records are written once and superseded, not edited silently; a divergence between code and architecture is
  recorded in the working log first and then reflected here.
- Content in these documents refers to ADR numbers and repository files only.

## Supersedes

None.
