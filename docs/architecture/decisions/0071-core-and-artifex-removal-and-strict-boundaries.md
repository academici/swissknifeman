# ADR 0071: core and artifex are removed and the module boundary check is strict

## Status

Accepted

## Context

The root `core/` package was a compatibility layer over `aicore`, and `packages/artifex` was retired. The boundary
check carried a baseline of known violations and transitional roots.

## Decision

- **Removal.** `core/` and `packages/artifex` are deleted after every consumer moved to `aicore` and to partner commands.
  Code outside the repository that imports `core` must import `aicore`. `aicore.util.paths.state_dir` is removed; use
  `aicore.state`.
- **Map.** In `configs/ecosystem-units.json` the foundation aliases, the transitional roots, the retired list and the
  foundation paths are empty, and no ownership row is transitional.
- **Strict check.** `python3 scripts/ecosystem-units.py check --strict` is green with an empty baseline, every module passes
  `standalone`, and CI runs the strict check.
- **Exceptions.** `path_allow` holds only data with a reason: sample strings in the boundary tests of planner and skiller,
  the site scripts of skiller, and the instruction catalog with its fixtures.
- **Instructions.** The catalog loses the scope `artifex`, and `harness instructions apply` drops the lock records of
  scopes that left the catalog. Root instructions no longer name `core/`.

## Alternatives considered

- Keeping `core/` as an alias for one more release: rejected, nothing in the repository imports it.
- Allowing path exceptions for code: rejected, a path in code is the coupling the check exists to stop.

## Consequences

- The history of the removed packages stays in git and in the older decision records.
- A new violation fails CI instead of growing a baseline.

## Supersedes

None.
