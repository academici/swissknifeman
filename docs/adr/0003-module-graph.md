# ADR 0003: Module graph and foreign-key direction

Status: proposed
Date: 2026-10-25

## Context
Bounded contexts need an explicit dependency order so that code imports and database foreign keys agree.

## Decision
Modules and `depends_on`: access; workspace(access); settings(—); artifacts(workspace); extensions(workspace, policy);
policy(access, workspace); runtimes(workspace, extensions); planning(workspace, artifacts, extensions);
context(planning, extensions, artifacts); execution(access, planning, workspace, artifacts, extensions, policy, context,
runtimes); integrations(workspace, artifacts, extensions, policy, runtimes); optional: knowledge(workspace),
learning(execution, knowledge, workspace, runtimes), exports(planning, execution, workspace). Every module owns one Postgres schema
`skm_<module>` (`settings` uses `skm_config`); FKs point only to modules it depends on and to `skm_core`. Reverse links go through events or
through tables in the consumer's schema.

## Alternatives considered
- One shared schema: rejected — ownership becomes implicit.
- No cross-schema FKs: rejected — integrity is the reason for the database.

## Consequences
Adding a dependency is a visible manifest change reviewed against this graph.

## Compatibility
n/a.

## Verification
Architecture test compares module manifests, imports and FKs parsed from migrations.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

E14 retains extensions → policy. The settings module owns skm_config, and the platform manifest owns skm_core; neither is an extra bounded context.
