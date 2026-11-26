# ADR 0007: Identity — UUIDv7 entity ids, display keys as aliases

Status: proposed
Date: 2026-10-25

## Context
Legacy identity equals layout: plan id = directory name, item id = file name, unit id local to item.

## Decision
Every entity has an application-generated UUIDv7 id independent of name, position and storage. Human keys
(`PLAN7`, `P2.4`, `P2.4/U1`, `D3`, `V2`) are display keys/aliases stored separately and unique within their scope.
Renaming or moving never changes identity. Entity identity is stable across plan revisions
(`plan_entity_identities`).

### Run scope parentage

A `RUN` scope shares its UUID with the run. A revision-backed run has its `PLAN` scope as its
direct parent. An ad hoc run has its `PROJECT` scope as its direct parent. In both cases,
the `RUN` scope inherits the parent's workspace.

`kernel.scopes.check_scope_parent` and `skm_core.check_scope_parent` in `0002_core_scopes.sql`
must accept `PLAN` and `PROJECT` as the two allowed parent kinds for `RUN`. Storage verification
and config inventory diagnostics must use that same rule. The scope registry creates the scope
before the run exists. The run record must validate the exact parent ID when it binds to that scope.
See [ADR 0008](0008-plan-draft-revision-run.md#run-persistence).

`platform/config/scopes.py` must accept both stored work chains in ancestry order.

| Run | Stored config scopes |
| --- | --- |
| Revision-backed | `INSTANCE → WORKSPACE → PROJECT → PLAN → RUN` |
| Ad hoc | `INSTANCE → WORKSPACE → PROJECT → RUN` |

Config resolution must use the actual ancestors of the run. The ad hoc chain inherits
project configuration directly and has no plan layer.

## Alternatives considered
- UUIDv4: rejected — no time ordering for indexes and keyset pagination.
- Database sequences: rejected — ids needed before the DB call; not portable between backends.

## Consequences
APIs accept typed references; ambiguous strings are errors.

## Compatibility
Legacy ids become aliases on import.

## Verification
Property tests: display key changes keep ids; uuid7 monotonic within a millisecond given the same entropy source.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).
