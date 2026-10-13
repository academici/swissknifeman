# ADR 0068: The instruction catalog holds its targets as data; the legacy run driver finds planner by lookup

## Status

Accepted

## Context

The scope targets of instruction files were a table in code, `harness run` looked for planner in a neighbouring folder
and kept a copy of its routing table.

## Decision

- **Catalog.** `scopes[].targets` of `catalog.json` (`catalog_version` 1.8.0) lists the target files of each scope; the
  code reads them from the catalog. The catalog and its fixtures are data that name modules, so they are `path_allow`
  entries of the boundary check with a reason.
- **Planner lookup.** `run/task_paths.py` tries `PLANNER_ROOT`, the deprecated `SKM_TASK_ROOT`, `PLANNER_PLAN_PY` and
  `planner` on `PATH`; there is no neighbour or monorepo step.
- **Models.** Model selectors come from `aicore.provider.models`; the invocation template comes from the model catalog.
  The Cursor routing rule is built from that catalog and no longer lists planner-owned routes; CLI permissions follow the
  command name.
- **Sections.** The module sections of the catalog state that a module imports only itself and `aicore` and reaches
  others through partner commands.

## Alternatives considered

- Keeping the target table in code: rejected, a module that leaves the repository would edit harness.
- Per-module catalogs: deferred until modules move out.

## Consequences

- The router rule of Cursor changed once.
- Adding a scope is a catalog edit plus a fragment, with no code change.

## Supersedes

None.
