# ADR 0014: Language-neutral contracts live in aicore

## Status

Accepted

## Context

Several modules share contracts (module manifest, events, errors, digests). Copying them or depending on `orch` for
them breaks ADR 0002.

## Decision

JSON Schema (draft 2020-12, with a concrete `$schema` and a versioned `$id`) is the source of truth; Python
implements it. Shared contracts live in `packages/aicore/schemas/<contract>/v<N>/`: the module manifest, the event
envelope, the error taxonomy, capability support levels, the canonical digest and the schema evolution policy.
`exec/v1` stays in `orch` as the orchestration contract but takes shared definitions from `aicore`. A separate
contracts module appears only when a non-Python consumer exists.

## Alternatives considered

- A separate contracts module or repository now: rejected, not needed while all consumers are Python and depend on
  `aicore`.

## Consequences

- Every new contract needs a JSON Schema; the inventory with owners and gaps is in `contracts.md`.
- The hub checks that every schema has `$schema` and a versioned `$id`.

## Supersedes

None.
