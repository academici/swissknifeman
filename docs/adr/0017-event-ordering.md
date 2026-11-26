# ADR 0017: Event ordering and SSE cursors

Status: proposed
Date: 2026-10-25

## Context
An autoincrement id does not reflect commit order; a client may skip a late-committed event.

## Decision
Each event has a per-stream sequence allocated under the stream row lock and a per-workspace sequence allocated
from `skm_core.workspace_event_counters` under a row lock in the same transaction. SSE cursors use the workspace
sequence. This serializes event writes per workspace — an accepted trade-off at the expected scale.

## Alternatives considered
- Global bigserial + visibility tricks: rejected — subtle gaps.
- External broker: rejected (no measured need).

## Consequences
Contention on very busy workspaces; revisit with a measurement trigger.

## Compatibility
n/a.

## Verification
Concurrency test: two parallel transactions never produce a gap visible to a cursor reader.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

E07 adds a separately locked event_streams counter for instance-feed global_position; a sequence cannot replace commit ordering. E19 requires cursor control frames and current authorization on reconnect.
