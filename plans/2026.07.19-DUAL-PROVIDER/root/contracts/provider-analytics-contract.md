provider-analytics-contract v1.0.0 / frozen

## Identity

Every normalized event MUST carry stable `provider_id`, `session_id`, `project_id`, and `event_id` values. IDs MUST be opaque strings with stable meaning inside their documented scope. Producers MUST NOT derive a cross-project identity from prompt, transcript, secret, or provider payload content. Reprocessing the same source event MUST preserve its `event_id`.

## Versioning

Every event MUST declare `contract_version: "1.0.0"`. Readers MUST accept only explicitly supported contract and reader schema versions. Producers MUST NOT silently reinterpret an existing semantic field. Additive semantic fields require an allowlist update; incompatible meaning requires a new contract version.

## Event envelope

The normalized envelope MUST contain only allowlisted semantic fields: `contract_version`, stable identity fields, `occurred_at`, `event_kind`, `outcome`, `metrics`, and `provenance`. `occurred_at` MUST be a UTC timestamp. `event_kind`, `outcome`, and metric names MUST come from a documented neutral allowlist. The envelope MUST NOT persist transcripts, prompt bodies, raw event bodies, resolved secret values, provider raw paths, provider event names, or provider payload shapes.

Normalized analytics events and their audit records MUST be append-only. Corrections MUST append a superseding event or audit entry and MUST NOT mutate prior events.

## Run report

A run report MUST be a deterministic projection over normalized events for one stable project/session scope. Its semantic candidates MAY include `tools`, `files`, `workflows`, `retrieval`, `devloop`, `maind`, `usage`, `reads`, and `errors` when supported by evidence and the allowlist. Missing evidence MUST remain absent or explicitly unknown; a reader MUST NOT fabricate a zero or inferred provider capability. Run reports MUST retain provenance for every contributing source event.

## Storage and retention

Normalized machine analytics MUST live under the project-local `.swissknife/analytics` home. Human-curated analyst state MUST live under the project-local `.swissknife/analyst` home. No normalized writer MAY write a provider-owned analytics home. Retention MUST be project-local, explicit, and append-only for events and audit data. Implementations MUST NOT add global telemetry or cross-project raw aggregation.

Human promotion behavior MUST remain unchanged: machine observations do not become curated analyst knowledge without the existing explicit human promotion step.

## Provider readers

Provider raw paths, provider event names, and provider payload shapes MUST appear only in explicit named reader sections and reader implementations. They MUST NOT appear in the neutral envelope, neutral goldens, store layout, or consumer API.

The named Claude reader MUST interpret the existing Claude `SCHEMA=2` line-streamed run-report source and map only evidenced, allowlisted semantics. The named Codex reader MUST map only semantics supported by the committed P5 hook/context support matrix and MUST NOT invent raw keys, events, or payload fields. Unknown provider input MUST fail with `ANALYTICS_UNKNOWN_PROVIDER`; an unsupported reader schema MUST fail with `ANALYTICS_UNKNOWN_SCHEMA`.

## Raw/privacy boundary

Normalized storage MUST NOT contain transcripts, prompt bodies, raw event bodies, or resolved secret values. Readers MUST redact before normalization and MUST fail closed with `ANALYTICS_REDACTION_FAILED` if redaction cannot be proven. Consumers MUST NOT dereference raw evidence as part of ordinary analytics reads. Implementations MUST NOT emit global telemetry or aggregate raw evidence across projects.

## Provenance and redaction

Every normalized event MUST carry local provenance containing exactly an opaque `raw_ref`, a lowercase SHA-256 `sha256`, `reader_id`, and `reader_version`. `raw_ref` MUST be project-local, opaque, and non-portable; it MUST NOT expose a provider raw path. `sha256` MUST describe the unchanged local source bytes. Provenance MUST NOT copy source content. Missing provenance MUST fail with `ANALYTICS_MISSING_PROVENANCE`; corrupt or hash-mismatched input MUST fail with `ANALYTICS_CORRUPT_EVENT`.

Redaction MUST happen before semantic fields are persisted. Audit entries MUST record the reader version and redaction outcome without recording redacted values.

## Diagnostics

The complete v1 diagnostic code set is exactly:

- `ANALYTICS_UNKNOWN_PROVIDER`
- `ANALYTICS_UNKNOWN_SCHEMA`
- `ANALYTICS_CORRUPT_EVENT`
- `ANALYTICS_MISSING_PROVENANCE`
- `ANALYTICS_REDACTION_FAILED`
- `ANALYTICS_LEGACY_INFERRED_PROVIDER`
- `ANALYTICS_MIGRATION_CONFLICT`

Diagnostics MUST be deterministic, safe to persist, and free of transcripts, prompt bodies, raw event bodies, resolved secret values, and provider payload fragments. Implementations MUST NOT substitute unversioned free-form diagnostic codes.

## Legacy compatibility

Legacy Claude `SCHEMA=2` data MUST be supported by dual-read/single-write behavior: readers MAY read the legacy source and the neutral store, but every new normalized event MUST be written only to `.swissknife/analytics`. When provider identity is inferred solely through the bounded legacy fallback, the reader MUST append an audit record with `ANALYTICS_LEGACY_INFERRED_PROVIDER`. Compatibility MUST NOT change source bytes or extend to unevidenced schemas.

## Migration

Migration MUST expose separate `plan`, `dry-run`, `check`, and `apply` operations. Apply MUST implement copy+verify: copy to a collision-safe destination, verify identity, content hash, contract validity, and audit output, then report success. Migration MUST be idempotent. Migration MUST leave source bytes unchanged and MUST never delete a source. A destination collision with non-identical content or identity MUST fail with `ANALYTICS_MIGRATION_CONFLICT`; migration MUST NOT overwrite it. Dry-run and check MUST make no source or destination data changes.

## Consumers

P6.4 consumers MUST read normalized analytics through this contract and explicit named readers. Consumers MUST branch only on documented semantic versions and diagnostics, never on provider raw paths, event names, or payload shapes. Consumers MUST preserve append-only audit semantics and the existing human promotion boundary. Consumers MUST NOT perform global telemetry or cross-project raw aggregation.

## Golden examples

Normalized Claude example:

```json
{
  "contract_version": "1.0.0",
  "provider_id": "claude",
  "session_id": "session-01",
  "project_id": "project-01",
  "event_id": "event-01",
  "occurred_at": "2026-07-22T00:00:00Z",
  "event_kind": "run_summary",
  "outcome": "ok",
  "metrics": {"tools": 3, "reads": 4, "errors": 0},
  "provenance": {
    "raw_ref": "local:source-01",
    "sha256": "1111111111111111111111111111111111111111111111111111111111111111",
    "reader_id": "claude-run-report",
    "reader_version": "1.0.0"
  }
}
```

Normalized Codex example:

```json
{
  "contract_version": "1.0.0",
  "provider_id": "codex",
  "session_id": "session-02",
  "project_id": "project-01",
  "event_id": "event-02",
  "occurred_at": "2026-07-22T00:01:00Z",
  "event_kind": "run_summary",
  "outcome": "ok",
  "metrics": {"usage": 1, "workflows": 1},
  "provenance": {
    "raw_ref": "local:source-02",
    "sha256": "2222222222222222222222222222222222222222222222222222222222222222",
    "reader_id": "codex-hook-context",
    "reader_version": "1.0.0"
  }
}
```

Goldens MUST contain semantic fields and opaque provenance only. They MUST NOT document provider raw keys, event names, payload shapes, prompt text, secret material, or source paths.

## Approval

D79 delegated authority accepts Alternative C: a neutral `.swissknife` store with explicit named readers and a bounded legacy fallback. D90 is frozen by this approval. Any incompatible change to identity, privacy, provenance, storage, migration, reader isolation, or consumer behavior MUST create a new versioned contract and decision; it MUST NOT mutate v1.0.0.
