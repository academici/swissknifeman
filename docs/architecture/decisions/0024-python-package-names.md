# ADR 0024: Python package names of modules

## Status

Accepted

## Context

Module import names are common words. A future pip publication could collide with other distributions.

## Decision

Import names stay `<id>` (`aicore`, `skiller`, `planner`, `orch`, `maind`, `analyst`, `harness`, `brain`). The module
id equals the folder name and the single top-level package in `lib/<id>/`; `scripts/ecosystem-units.py check`
enforces it. Module `bin/` wrappers put their own library and `aicore` first on `sys.path`, so a same-named pip
package in the environment cannot shadow a module. Future distribution names are `skm-<id>`. A namespace `skm.<id>`
is a separate decision, taken on the trigger "pip publication of modules" or "in-process extensions"; the rename
is then one mechanical change with a shim for one minor release.

## Alternatives considered

- A namespace package `skm.<module>` now.
- Unique import names `skm_<module>` now.
  Both would double the work of the foundation and rename stages without a consumer.

## Consequences

- The collision risk exists only for pip installs and is closed by the trigger and by `sys.path` order.

## Supersedes

None.
