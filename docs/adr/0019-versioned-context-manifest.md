# ADR 0019: Versioned, two-phase context manifest

Status: proposed
Date: 2026-10-25

## Context
The model input must be explainable and reproducible, but part of it lives on the control plane (revision, resources,
decisions) and part in the host checkout (repository instructions, repository files).

## Decision
Context is assembled in two phases: `context.public.assemble_draft` on the control plane (blocks with content + list of host
inputs) and pure `finalize` on the host (reads host inputs safely, applies the budget, renders the prompt), confirmed by
`context.finalize_manifest`, which re-checks digests and the budget decision. Manifests are immutable once final and
record source, version, digest, selection reason, trust and token estimate per block. Host block content stays on the
host unless `context.store_host_block_content` is enabled. Context is assembled after routing; a runtime fallback creates
a new manifest.

### Manifest ownership and assembly permission

`0019_context_manifests.sql` must accept two forms of `context_manifests.owner_ref`. The form and
value are fixed at draft creation and immutable through finalization.

| Owner form | Binding |
| --- | --- |
| `step:<step_id>` | `step_ref` must identify the same execution step. One manifest is allowed per step. |
| `standalone:<principal_id>` | The UUID identifies the principal that assembled the draft. `step_ref` must be SQL `NULL`. |

Every standalone manifest must belong to a workspace and project. Plan, revision and entity
references are optional for standalone assembly. When provided, they must identify valid context
within that project, and an entity reference must resolve within the selected revision. The same
two-phase assembly and finalization rules apply to both owner forms.

Standalone assembly requires the `context.assemble` RBAC permission on the target project. Declare
the permission in `src/skm/modules/context/permissions.py` and register it in the access permissions
catalog at `src/skm/modules/access/permissions.py`. Standalone finalization must verify the immutable
principal owner and the principal's `context.assemble` permission on the project. Step finalization
continues to require `worker.claim` and validation of the current execution claim.

### Host-private episodic memory

Episodes and their summaries from `LocalSqliteMemoryStore` are `HOST_PRIVATE`. Hub-run context assembly
omits memory hits with this classification before any manifest block, text digest or prompt is written. The host
store has no retrieval path into Hub runs or cloud LLM requests. The
`context.store_host_block_content` setting applies only to the manifest's ordinary host input blocks.

Start `skm mcp --local-memory-session UUID` with a human credential and an embedded profile to open a
trusted host-only stdio session. It exposes only `skm_local_memory_record`, `skm_local_memory_search` and
`skm_local_memory_summarize`, subject to the session's project permissions. HTTP-backed, assignment and
ordinary MCP sessions have no access to these tools. The caller owns the session UUID and uses its local
run ID when running within a local run.

A read or summary that returns episodes writes a durable local consumption receipt before delivering any
episode data. The receipt survives episode expiration. Host-private provenance remains local in
the run's consumption marker or the memory session's receipt. The local memory store fails closed
when it cannot verify a receipt.

## Alternatives considered
- Send checkout files to the server: rejected (privacy, size).
- Assemble everything on the host: rejected (host would need DB access).

## Consequences
One extra command per agent step.

## Compatibility
Legacy prompt manifest block kinds map to v2 block types in [`modules/context/`](../../src/skm/modules/context/).

## Verification
Tamper test: a changed control-plane block digest is rejected with `CONTEXT_MANIFEST_TAMPERED`.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

For step-owned manifests, E21 uses the context-owned `ContextOwnerGuard` with an adapter delegating
to `execution.public.require_current_context_owner`. Intrinsic replay validates the current claim.
Context depends on its own guard port. Generic idempotency keys are forbidden for finalization.
