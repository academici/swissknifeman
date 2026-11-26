# ADR 0026: The folder-is-a-module rule through a pinned root common instruction

## Status

Accepted

## Context

Root common instructions are projected on demand and no provider receives them by default, yet the root agent
instructions must state that a folder is a module.

## Decision

A new common section `root.module-folders` is added to the harness catalog, and `ROOT_PINNED_COMMON_IDS` in
`instructions.py` lists the common ids that are always projected for the root scope, to every provider
regardless of `project_common`. The remaining root common sections stay on demand. The catalog version is raised by
a minor step and the provider instruction contract describes pinning.

## Alternatives considered

- Project all root common sections again: rejected, it inflates the first-turn context.
- Copy the rule into each provider's extension section: rejected, four copies drift.

## Consequences

- Adding a pinned id is a catalog change with a contract update and regenerated root files.
- The context budget gate still applies to the root files.

## Supersedes

None.
