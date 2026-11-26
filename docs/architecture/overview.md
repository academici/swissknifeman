# Architecture overview

Paths are relative to the product root; there is no nested product directory.
[ADR 0001](../adr/0001-modular-monolith-and-worker.md) records the process split.

## Processes

| Process | Intended command | Access and responsibility |
|---|---|---|
| Control plane | `skm serve` | Database, blobs, API/SSE and background services |
| Worker | `skm worker` | Host worktrees, runtimes and scoped credentials; runs assignments outside the API process |
| CLI | `skm …` | Embedded database access through the bus, or HTTP access through the client |
| MCP | `skm mcp` | Agent tools using the same client boundary as CLI |
| PostgreSQL | Local or server installation | Sole production state backend |
| Web | Browser client | HTTP API and SSE; no direct storage access |

Local mode combines a local database, control plane and worker. Server mode keeps
the database and API on the server while the worker makes outbound HTTPS requests.
Both use the same contracts. These are target deployment behaviors, not P00 claims.

## Command flow

```text
surface → SkmClient (embedded | http) → application bus
translate_errors → validate_dto → uow.begin → resolve_scope → authorize
  → load_config → idempotency → handler → receipt → audit → commit
```

All database reads occur inside the UoW. Authorization and configuration use the
current transaction. State, events, outbox, receipt and allowed audit commit
together. A denied command rolls back; denied audit uses a separate short UoW.
Retries after serialization/deadlock failures open a fresh UoW and repeat scope,
authorization and configuration resolution. External host effects stay outside
bus handlers. Idempotency modes are `REQUIRED`, `OPTIONAL` and `FORBIDDEN`.

## Calls and events

Synchronous cross-module work uses `public.py` along the declared dependency graph.
Events describe facts and feed subscribers, SSE and hooks through the outbox.
Per-stream `stream_seq` and locked per-workspace counters preserve cursor order.
E07 adds a separately locked `event_streams` counter for the instance feed;
a database sequence alone does not preserve commit order.
Subscriber receipts make delivery idempotent. Runtime text deltas belong in
transcripts and an ephemeral live channel, not authoritative domain events.

## Composition and extension

Bootstrap constructs explicit immutable registries and adapter bindings.
No import side effects or global service locator register dependencies.
Bus handlers use repository/control-plane ports; host operations use host gateways
and `SkmClient`. Typed gateway lookup is `ctx.gateways.get(Port)`.
Host stages receive only their declared `StageDeps`/`StageClient` boundary.

| Extension | Contract | Stable consumers |
|---|---|---|
| Runtime | `AgentRuntime` and capability manifest | Planning, execution, storage and review |
| Client projection | `IntegrationTarget` | Extensions and policy |
| Check | `CheckRunner` with a declared kind/schema | Execution orchestration |
| Workflow stage | Trusted `StageHandler` and parameter schema | Deterministic engine |
| Skill, steering, workflow, profile | Versioned resource data | Product code |
| Storage | Module ports and their contract suites | Domain and application |

Trusted plugins load only from operator-allowed `skm.plugins` entry points through
the stable `skm.plugin_api`. Resources cannot expand permissions.
See [layers and modules](layers-and-modules.md), [data](data-model.md) and
[runtime boundaries](runtimes-context-extensions.md).
