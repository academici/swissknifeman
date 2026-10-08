# ADR 0031: The model catalog belongs to aicore

## Status

Accepted

## Context

The mapping from a model class (`economy`, `implementation`, `frontier`) and an effort to a concrete model sat in
`packages/task/configs/command-routing.json`. Task, harness and orch read it, so it is not planner knowledge.

## Decision

The canon is `packages/aicore/configs/model-catalog.json` (`model-catalog/v1`), read through
`aicore.provider.models` (`load_model_catalog`, `default_model_catalog_path`, `select_model`, `select_effort`,
`inventory`). The fields `class_selectors`, `effort_selectors` and `model_inventory` in `command-routing.json` stay
as a transitional copy because the command catalog schema of task does not change here. A test of task compares the
copy with the canon and tells the author to update both. The copy is removed when the planner reads `aicore`
(stage P9); orch moves in P10 and harness in P11.

## Alternatives considered

- Delete the copy and move all readers now: rejected, readers get `aicore` only in their stages.
- Keep the catalog in task: rejected, at least two other modules read it.

## Consequences

- One place to add a model; the parity test catches drift during the window.

## Supersedes

None.
