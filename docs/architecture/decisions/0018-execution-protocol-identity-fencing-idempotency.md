# ADR 0018: Execution protocol: event identity, fencing, idempotency, immutable launch plan

## Status

Accepted

## Context

The execution contract needs identity and ordering rules before an engine is built on it.

## Decision

A run event gets `event_id` (deduplication), `causation_id`, `correlation_id` and `owner_epoch`. Invariants: `attempt`
`seq` and terminal state are monotonic; redelivery is idempotent; an event of an old epoch is rejected; cancel is a
request and `cancelled` is reported only after a confirmed stop; `unknown_outcome` never turns into `failed`. The
local engine fences with a lock holding pid and epoch, and resume raises the epoch. Idempotency keys:
`submission_id`, the launch-plan digest, `attempt_id` and `effect_id` in an effect receipt. `prepare` is pure and
returns an immutable launch plan with digests of input, policy, roles, catalog and module versions, the chosen
binding and decisions; `prepare --dry-run` returns proof and `explain` shows the reasoning. Large data travels as
artifacts by digest. There is one execution owner per run and per plan-item attempt.

## Alternatives considered

- Add these fields while implementing the engine: rejected, the contract would change under running engines.

## Consequences

- The change is additive to `exec/v1` and is implemented in the orchestration stage; the engine itself is separate work.
- Most invariants already exist in the engine port document.

## Supersedes

None.
