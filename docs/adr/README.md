# Architecture decision records

Records 0001–0024 are the architecture decisions. Each record keeps its original
decision date, the 2026-10-27 materialization date, an explicit status, and the
addenda written in that record. Proposed records remain proposed; ADR 0024 is
accepted. These records do not promote a proposed status by blanket.
Changing an ADR status requires an explicit acceptance or supersession decision.
Manual review status is tracked separately in [status](../status.md).
Records 0025 and later use the date and status stated in each record.
Names, layers and module boundaries follow
[layers and modules](../architecture/layers-and-modules.md).

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-modular-monolith-and-worker.md) | Modular monolith in one distribution plus a separate worker process | proposed |
| [0002](0002-layers-and-import-rules.md) | Layers and import rules enforced by architecture tests | proposed |
| [0003](0003-module-graph.md) | Module graph and foreign-key direction | proposed |
| [0004](0004-sync-core-async-edge.md) | Synchronous core, async only at the HTTP edge | proposed |
| [0005](0005-postgres-only-backend.md) | PostgreSQL is the only production state backend in v2.0 | proposed |
| [0006](0006-psycopg-explicit-sql-migrations.md) | psycopg 3, explicit SQL and an own forward-only migration runner | proposed |
| [0007](0007-identity-uuidv7-display-keys.md) | Identity — UUIDv7 entity ids, display keys as aliases | proposed |
| [0008](0008-plan-draft-revision-run.md) | Plan / Draft / Revision / Run separation | proposed |
| [0009](0009-command-transaction.md) | One command, one transaction — state, events, outbox, idempotency receipt | proposed |
| [0010](0010-one-config-engine.md) | One configuration engine | proposed |
| [0011](0011-json-schema-source-of-truth.md) | JSON Schema is the source of truth for contracts | proposed |
| [0012](0012-dependency-policy.md) | Dependency policy | proposed |
| [0013](0013-deterministic-engine-workflows-as-data.md) | Deterministic orchestration engine; workflows as data | proposed |
| [0014](0014-leases-fencing-environments.md) | Leases with fencing tokens; one execution environment per attempt | proposed |
| [0015](0015-extensions-data-plugins-trusted.md) | Extensions are data; executable plugins are trusted-only | proposed |
| [0016](0016-integrations-vs-runtimes.md) | Client integrations are separate from agent runtimes | proposed |
| [0017](0017-event-ordering.md) | Event ordering and SSE cursors | proposed |
| [0018](0018-review-explicit-contract.md) | Review is an explicit, mandatory contract | proposed |
| [0019](0019-versioned-context-manifest.md) | Versioned, two-phase context manifest | proposed |
| [0021](0021-bus-handlers-and-host-operations.md) | Two kinds of application code — bus handlers and host operations | proposed |
| [0022](0022-plugins-stable-api.md) | Plugins through entry points with a stable `skm.plugin_api` | proposed |
| [0023](0023-staged-blob-upload.md) | Bytes enter only through staged blob upload | proposed |
| [0024](0024-research-source-component.md) | Research sources are a separate plugin component kind | accepted |
| [0025](0025-integrations-zero-shadowing-and-presets.md) | Zero-shadowing client projections and project and package presets | proposed |
| [0026](0026-local-llm-router.md) | Loopback-only LLM router and versioned provider pool | proposed |

## Record format

Each numbered ADR retains Context, Decision, Alternatives considered,
Consequences, Compatibility and Verification. Add a date and an explicit
status. Superseded records name their successor; keep numbering continuous.
No generated reference pages are assumed by these records.
