# ADR 0009: task becomes planner, with aliases; plan URNs do not change

## Status

Accepted

## Context

The name `task` is vague next to the other modules. Plans in many projects carry `urn:swissknifeman:task:plan:*`.

## Decision

The module becomes `packages/planner` with commands `/planner:*` and the `PLANNER_ROOT` variable. For one minor
release `/task:*` and `SKM_TASK_ROOT` are still accepted with a warning. The plan schema URNs
`urn:swissknifeman:task:plan:*` do not change.

## Alternatives considered

- Keep the name `task`: rejected for clarity.
- Change the URNs together with the name: rejected, it would break plans in every project.

## Consequences

- Until the rename, the module keeps id `task`: the id must equal the folder and the import package (ADR 0024).
- Aliases have a window and a removal step (ADR 0020).

## Supersedes

None.
