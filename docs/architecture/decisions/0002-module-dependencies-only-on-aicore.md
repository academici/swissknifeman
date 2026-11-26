# ADR 0002: A module depends only on its own library and on aicore

## Status

Accepted

## Context

Helpers were shared between `skiller` and `task` through `core/`, and modules reached into each other by import
and by path. That makes modules impossible to test or move alone.

## Decision

Any module imports only its own `lib/<id>/` and `aicore`. `aicore` depends on nobody. The hub root assembles
everything. All other links are bridges or events (ADR 0003).

## Alternatives considered

- Keep `core/` importable by `task` and `skiller` only: rejected, it is the coupling this change removes.

## Consequences

- Boundaries are mechanical: `scripts/ecosystem-units.py check` rejects imports and path references across
  modules, with a baseline for violations that exist today.
- Code used by two or more modules moves into `aicore` (ADR 0004).

## Supersedes

Supersedes the earlier orchestration-preparation decisions that allowed `core` to be used by `task` and `skiller`.
