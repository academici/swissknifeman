# ADR 0001: Modules are isolated folders with a manifest; no new repositories yet

## Status

Accepted

## Context

The ecosystem lives in one repository but is meant to become several: some modules will move to their own
repositories later. The layout has to behave like separate repositories now, without creating them.

## Decision

Every capability is a module in `packages/<id>/` (`aicore`, `skiller`, `planner`, `orch`, `maind`, `analyst`,
`harness`, `brain`) with one contract: a `unit.json` manifest that declares `destination: own-repo` or `hub`.
Bridges between modules live in `bridges/` of the hub. `core/` dissolves into `aicore` and `analyst`, and
`packages/artifex` is retired. The rule "a folder is a module" is written into the root agent instructions
through the harness instruction catalog (ADR 0026).

## Alternatives considered

- Separate repositories right away: rejected, the foundation and the contracts are not stable enough to version
  independently.

## Consequences

- A module can be checked, tested and, later, moved on its own.
- Cross-module access is visible and checkable (ADR 0002, ADR 0020).
- Moving a module out is a later, separate decision; publishing to marketplaces waits for it.

## Supersedes

None.
