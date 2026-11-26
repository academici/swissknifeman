# ADR 0002: Layers and import rules enforced by architecture tests

Status: proposed
Date: 2026-10-25

## Context
Legacy code mixes IO, discovery, persistence and rules (e.g. `planner/plan/store.py` holds the model, project
discovery, checkout binding, layout, locking, validation, serialization and the event log).

## Decision
Layers: kernel → platform → module domain → module application (+ports, public) → adapters → entrypoints →
bootstrap. Rules are listed in [layers and modules](../architecture/layers-and-modules.md) and checked by `tests/architecture/`
(AST-based, no external dependency): domain purity, facade-only cross-module imports, config access only
through the engine, provider names only in adapters, no grab-bag file names, file size limits.

## Alternatives considered
- import-linter: acceptable, but an own AST test also checks names, sizes and provider literals in one place.
- Rules in README only: rejected — legacy experience shows they erode.

## Consequences
New code cannot drift silently; exceptions require an ADR and an allowlist entry with a reason.

## Compatibility
n/a (new tree).

## Verification
`make arch` is part of `make check`; a fixture module with deliberate violations proves each rule fails.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

E33 keeps early contracts declarative until behavior is implemented. The layer matrix and precise exceptions are in [layers and modules](../architecture/layers-and-modules.md) and the [contract inventory](../architecture/contracts.md).
