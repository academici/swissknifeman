# ADR 0014: Leases with fencing tokens; one execution environment per attempt

Status: proposed
Date: 2026-10-25

## Context
A `running` flag cannot distinguish a live task from a dead worker; fencing protects only operations that check
the token.

## Decision
Workers claim assignments and receive a lease with a monotonic fencing token; every worker command carries
(assignment, attempt, worker, token) and is rejected with `LEASE_LOST` when stale. Every attempt has its own
execution environment (git worktree); competing attempts never share a working tree; integration into target
branches is serialized per repository. Heartbeat failure puts the worker into stop mode. External side effects use
tool intents with `outcome_unknown` and reconciliation; exactly-once is not promised.

## Alternatives considered
- Shared checkout with locks: rejected — a stale process can still corrupt files.

## Consequences
Disk use per attempt; cleanup policy for environments.

## Compatibility
Generalizes legacy ADR 0018 (identity, fencing, idempotency).

## Verification
Recovery tests in `06` §13.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

E21 rechecks context ownership in the same UoW. E28 permits same-attempt recovery only under the documented no-start/reap conditions. E44 requires exact immutable effect requests, journals and receipts; trailers only cross-check them. E56 treats silence and unknown telemetry as incomplete evidence.
