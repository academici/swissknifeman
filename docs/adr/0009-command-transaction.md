# ADR 0009: One command, one transaction — state, events, outbox, idempotency receipt

Status: proposed
Date: 2026-10-25

## Context
Legacy writes documents and appends `log.jsonl` separately; a crash can leave state without event or vice versa.

## Decision
The application bus executes each command in one Unit of Work. In the same transaction it writes aggregate
changes (conditional on expected versions), domain events, outbox rows, the idempotency receipt and the audit
record. External effects never happen inside the transaction; they go through tool intents and receipts.

## Alternatives considered
- Remote unit of work over HTTP: rejected — network failures between steps create ambiguity.

## Consequences
HTTP clients call whole server-side commands; retries reuse idempotency keys.

## Compatibility
n/a.

## Verification
Recovery tests: failure before commit leaves nothing; retry after commit returns the stored result.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

E05 resolves scope, authorization and configuration in the current UoW before idempotency. Idempotency modes are REQUIRED, OPTIONAL and FORBIDDEN; secret responses never enter receipts.
