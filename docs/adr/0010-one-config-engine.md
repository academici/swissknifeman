# ADR 0010: One configuration engine

Status: proposed
Date: 2026-10-25

## Context
Legacy has one real layered engine (`aicore.config`: defaults, machine, project, env, --config, flags; per-key
layer permissions; provenance) but no workspace or plan level, and at least nine bypassing loaders plus ~25
hand-rolled environment variables.

## Decision
All settings of all modules are declared as JSON Schema sections with `x-skm` metadata (chain, allowed levels,
merge strategy, reload class, override, sensitivity, portability, lock, UI hints). One resolver turns layers
(`default, pack, instance, workspace, project, plan, run, invocation`; host chain `default, pack, instance, host,
invocation`) into an effective config with provenance. Levels above `pack` are stored in PostgreSQL and edited
through commands (CLI, API, web). Only a minimal bootstrap file/env locates the database. Modules read settings
only through typed section views. Run-frozen keys are snapshotted into the execution bundle.

## Alternatives considered
- Files as the primary store: rejected — owner wants DB/front editing; files only for bootstrap and import/export.

## Consequences
The web Settings page is generated from the registry.

## Compatibility
Legacy semantics kept: explicit unset, arrays replace by default, maps merge, explicit append, per-key level
permission, explain, secret references.

## Verification
Tests in `04` §10; architecture test forbids other config readers.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

E30 permits pack configuration only for builtin/operator trust and prevents project/plan/run from widening default ceilings. E55 limits run reconfiguration to a fixed allowlist at a drained CAS checkpoint.

I-10.1b (`[web_auth]` pre-DB process config): HTTP web authentication admission (`[web_auth]` in `bootstrap.toml`, supported in both single-instance and named `[instances.<name>.web_auth]` profiles, with `SKM_WEB_AUTH_MODE` environment override) is explicitly part of the pre-database bootstrap document (`urn:skm:config:bootstrap:v1`), not a PostgreSQL settings section in `api.v1.json`. The API process must decide its admission mode (`admin_login` vs loopback-only `none`), reverse-proxy peer trust (`forwarded_allow_ips`), cookie/session parameters, and pre-auth rate limits before opening the database and must fail closed whenever PostgreSQL is unavailable; duplicating `[web_auth]` in `api.v1.json` is forbidden.
