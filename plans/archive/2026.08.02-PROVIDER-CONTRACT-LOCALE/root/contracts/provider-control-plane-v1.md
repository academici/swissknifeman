# Provider control-plane contract

**Version:** v1.0.0
**Status:** frozen
**Owner:** repository owner
**Approval:** D73, 2026-08-14
**Predecessors:** frozen provider configuration v1.0.0, capability v1.0.0, and artifact v1.3.0 contracts

## Purpose

This contract defines one JSON-safe, provider-neutral read model for desired provider state,
adapter-scoped last-applied provenance, fresh observation, derived drift, diagnostics, and an
aggregate result. It composes the predecessor sources of truth; it does not replace them:

- the provider-config resolver owns desired selection and leaf provenance;
- the capability manifest owns Provider IDs, Capability IDs, Native Extension IDs, support
  levels, and catalog version;
- artifact locks own managed artifact identity, source/rendered hashes, and boundaries;
- each adapter owns only its provider-qualified apply and observation evidence.

Rendered provider output is never canonical intent. This contract authorizes no apply,
repair, migration, carrier write, provider-target write, fleet write, or credential access.
Read, check, and schema validation are strictly no-write.

Normative words `MUST`, `MUST NOT`, `SHOULD`, and `MAY` are literal.

## Vocabulary and identities

`desired` is the complete materialized result of the frozen provider-config resolver. A
provider row is keyed by the stable Provider ID from the observed capability catalog.
`last_applied` is evidence from one successful committed provider apply. `observed` is fresh,
provider-qualified evidence from one read/check pass. `status`, `drift`, and `aggregate` are
derived values and MUST NOT be accepted as user-authored configuration.

Stable identity fields and machine codes use compact English literals. Only a diagnostic
`message` is human-renderable and MAY be localized later. Localization MUST preserve severity,
code, path/source identity, provider identity, and ordering.

Digest fields use `sha256:<64 lowercase hex>`. Project IDs and opaque operation/evidence IDs
are non-secret stable identifiers, never absolute paths. Raw provider payloads, config values,
credentials, tokens, environment values, host roots, and rendered bytes MUST NOT enter this
envelope.

## Result envelope

Every operation returns exactly:

```json
{
  "contract_version": "1.0.0",
  "result": null,
  "diagnostics": []
}
```

The envelope has exactly `contract_version`, `result`, and `diagnostics`.

- On schema/input failure, `result` MUST be `null` and `diagnostics` MUST contain at least one
  `error`. No partial desired/provider/aggregate value is returned.
- On success, `result` MUST be complete and top-level diagnostics MUST contain no `error`.
  Warning/info diagnostics do not authorize a write.
- Unknown fields, identities, versions, enum values, and incomplete provider sets fail closed.

A successful `result` has exactly:

| Field | Contract |
|:--|:--|
| `project_id` | Stable non-secret project identity; no slash or absolute path. |
| `desired` | Complete `DesiredSnapshot` below. |
| `providers` | One row for every Provider ID in `desired.selection`, sorted by Provider ID. |
| `aggregate` | Deterministic aggregate derived from those exact rows. |
| `evaluated_at` | UTC RFC 3339 `...Z` timestamp used only for freshness evaluation. |

Timestamps are evidence metadata. They MUST NOT enter `desired.semantic_digest`, artifact
source/rendered hashes, or any other semantic identity.

## DesiredSnapshot

`desired` has exactly:

```json
{
  "provider_config_contract_version": "1.0.0",
  "capability_catalog_version": "1.0.0",
  "selection": {},
  "provenance": [],
  "semantic_digest": "sha256:..."
}
```

`selection` is the frozen `EffectiveProviderConfig.selection` projection. It is non-empty and
each provider has exactly `enabled`, `capabilities`, and `native_extensions`; `enabled` is a
boolean and the two maps contain only explicitly selected boolean leaves. Missing is not
rewritten as explicit false.

Every materialized leaf has exactly one provenance record with exact fields
`effective_path`, `source`, `source_path`, and `explicit`. `source` has exact fields `kind`,
`id`, `carrier`, and `path` from the frozen config contract. Provenance is sorted by
`effective_path`; map containers have no synthetic winner.

`semantic_digest` is SHA-256 of UTF-8 canonical JSON for the other four `desired` fields:
object keys sorted, separators `,` and `:`, Unicode unescaped, array order preserved. It
therefore covers desired values and provenance but excludes itself and all timestamps.

## Provider status row

Each provider row has exactly:

| Field | Contract |
|:--|:--|
| `provider_id` | Exact key from `desired.selection`. |
| `selected` | Exact copy of `desired.selection[provider_id].enabled`. |
| `desired_digest` | Exact copy of `desired.semantic_digest`. |
| `last_applied` | `null` or complete successful-apply evidence. |
| `observed` | `null` or complete fresh/check evidence. |
| `status` | One derived Provider Status literal. |
| `diagnostics` | Provider-qualified structured diagnostics. |

### Last-applied evidence

A non-null `last_applied` has exactly `apply_id`, `desired_digest`,
`capability_catalog_version`, `artifact_set_digest`, `artifacts`, and `recorded_at`.
`desired_digest` and catalog version MUST match the desired snapshot. `artifacts` is sorted by
`artifact_id`; every record has exactly `artifact_id`, `adapter_id`, `adapter_version`,
`target_path`, `source_hash`, and `rendered_hash` from a successful committed artifact plan.
`recorded_at` is metadata and does not alter those hashes.

### Observed evidence

A non-null `observed` has exactly:

| Field | Closed value/meaning |
|:--|:--|
| `observation_id` | Stable opaque identity of one provider read/check. |
| `provider_version` | Observed provider/adapter version string, not a Provider ID. |
| `observed_at`, `fresh_until` | UTC RFC 3339 metadata. |
| `freshness` | `fresh` · `stale` · `unknown`. |
| `trust` | `trusted` · `untrusted` · `unknown`; evidence for Project Trust only. |
| `capability` | `satisfied` · `unsupported` · `unknown`; derived from the capability catalog and selected requirements. |
| `artifacts` | `clean` · `drifted` · `unknown`; derived from artifact observations. |
| `evidence_digest` | Digest of the adapter-owned redacted evidence set. |

The three security axes remain independent. `trust` MUST NOT be inferred from approval policy
or sandbox boundary, and those axes do not enter this status field. An adapter SHOULD refresh
all contract-declared evidence it can observe, but completeness means coverage of its declared
evidence contract, not omniscience over provider or host state.

## Deterministic provider status

Provider Status is exactly one of:

`not-selected`, `ready`, `unapplied`, `observation-missing`, `observation-stale`, `drifted`,
`unsupported`, `untrusted`, `unknown`, `error`.

The first matching rule wins:

1. `selected=false` → `not-selected`; `last_applied` and `observed` MUST both be null.
2. any provider diagnostic with severity `error` → `error`.
3. `observed.capability=unsupported` → `unsupported`.
4. `observed.trust=untrusted` → `untrusted`.
5. `last_applied=null` → `unapplied`.
6. `observed=null` → `observation-missing`.
7. `observed.freshness=stale` → `observation-stale`.
8. any observed axis is `unknown` → `unknown`.
9. `observed.artifacts=drifted` → `drifted`.
10. otherwise → `ready`.

Unsupported, untrusted, unknown, disabled/not-selected, and error are never aliases. A stale
row cannot be called ready even if its last-applied hashes match.

## Aggregate status

`aggregate` has exactly `status`, `selected_provider_ids`, and `provider_statuses`.
Selected IDs are sorted. `provider_statuses` contains every provider row with its exact derived
status. Aggregate Status is exactly one of `ready`, `unknown`, `drifted`, `blocked`, `error`,
or `no-providers-selected`, using the first matching rule:

1. no selected provider → `no-providers-selected`;
2. any selected provider is `error` → `error`;
3. any selected provider is `unsupported` or `untrusted` → `blocked`;
4. any selected provider is `drifted` or `unapplied` → `drifted`;
5. any selected provider is `observation-missing`, `observation-stale`, or `unknown` → `unknown`;
6. every selected provider is `ready` → `ready`.

Success of one selected provider never masks a non-ready selected peer.

## Capability negotiation

Negotiation is a pure, deterministic pre-render operation. It consumes the complete frozen
capability-manifest record (`providers` carry `id` and `display_name`; capabilities carry `id`,
`intent`, and provider support with evidence/diagnostic plus level-specific `binding` or
`adapter_id`; adapted support requires `adapter_id` and MAY additionally carry predecessor-valid
non-empty `binding`, and requires non-empty unique limitations and evidence), the complete frozen
P1.1 `DesiredSnapshot` selection map and leaf provenance, and
one explicit adapter descriptor. It MUST NOT discover adapters from the filesystem, reread config carriers,
inspect rendered output, or use another provider's result as support.

Ownership conformance additionally runs its frozen declared probes against the repository's actual
`configs/provider-capabilities.json` and the complete `mixed-freshness` producer result from the
P1.1 `schema-positive.json`. Fixture-local manifests are supplementary. A valid catalog support
change that alters a probe outcome is drift and fails the stage; incomplete producer provenance is
an input failure rather than a fixture fallback.

The descriptor provider, selection provider, and manifest provider row MUST match. Explicit
capability decisions win over catalog support: explicit `false` is denied even when the manifest
level is `native`; explicit `true` or a missing decision continues to the manifest record. Required
requirements are evaluated by capability ID and block render in this exact code order:

1. `NEG_PROVIDER_DISABLED`;
2. `NEG_PROVIDER_MISMATCH`;
3. `NEG_REQUIRED_DENIED`;
4. `NEG_REQUIRED_MISSING`;
5. `NEG_REQUIRED_UNSUPPORTED`;
6. `NEG_REQUIRED_LEVEL_REJECTED`;
7. `NEG_NATIVE_EXTENSION_INVALID`.

Within one code, subject IDs sort lexicographically. Every result carries the exact `provider_id`,
including blocked results, so diagnostics, labels, limitations, and extensions stay qualified.
The result is complete: `blocked` returns the
ordered required diagnostics and no partial render plan; `ready` returns every satisfied required
requirement, every provider-qualified optional limitation, and every enabled descriptor-owned
Native Extension. Optional denied, missing, unsupported, or level-rejected requirements remain
explicit limitations and never borrow a peer provider's support.

Native Extensions are checked only after common required capabilities. They remain separate from
the common capability matrix, use the exact provider namespace, and cannot satisfy a common
Capability requirement.

## Provider-qualified support presentation

`native`, `adapted`, and `unsupported` remain the only Support Levels. The words `supported`,
`degraded`, and `exclusive` are derived presentation labels, never stored support values:

- `supported`: the provider's required common capabilities negotiated without a blocker;
- `degraded`: additionally present when satisfied support is adapted, a satisfied support record
  has limitations, or an optional limitation exists;
- `exclusive`: additionally present only when an enabled provider-owned Native Extension exists.

The underlying levels, limitations, extensions, and provider identity remain visible. Aggregate
presentation is `blocked` whenever any selected provider negotiation is blocked; a ready selected
peer never masks it. A missing selected provider row is invalid rather than `not-selected`.
Aggregate selected Provider IDs use the provider grammar, are unique and lexicographically sorted,
and equal the provider-outcome key set exactly.

## Ownership and provider isolation

`artifacts/P1-provider-ownership-capability-matrix.json` is the exhaustive machine source for the
declared carrier families: provider config, capability manifest, adapter registry, canonical
sources, skill publication, normalized analytics, rendered targets, locks, status/evidence, and
human diagnostics. Every carrier pattern has
exactly one owner plus explicit read, write, derived-from, and forbidden-use sets. Its Markdown
counterpart is generated deterministically and is not independently editable.

Provider-parameterized carrier patterns use `{provider_id}`. The pattern is intentionally open to
any stable manifest Provider ID; there is no shared Claude/Codex enum ceiling. An adapter may read
canonical sources, the capability manifest, effective selection, its own descriptor, and its own
managed evidence. It may write only its matching projection plan, managed target boundary,
provider-scoped evidence/status, and matching lock through the artifact transaction.

Cross-provider target/lock/evidence/status read or write, output-to-output conversion, stale lock as
intent, diagnostic as authorization, and rendered output as canonical source are all invalid.
Check, negotiate, audit, schema validation, and fixture self-test are strictly no-write.

The provider-neutral Skill Core is frozen separately in `skill-core-v1.md`; additive registration,
projection, negotiation, and third-provider seams are frozen in
`provider-skill-adapter-v1.md`. Provider adapters add native mechanics without replacing shared
meaning.

## Diagnostics

Every diagnostic has exactly:

```json
{
  "severity": "error|warning|info",
  "code": "PCP_STABLE_CODE",
  "message": "human-renderable text",
  "source_ref": "stable non-secret identity"
}
```

Diagnostics are ordered by severity (`error`, `warning`, `info`), then `source_ref`, then
`code`. Codes and source references are stable machine fields; only `message` may localize.
The schema checker emits these closed refusal codes:

| Code | Meaning |
|:--|:--|
| `PCP_VERSION_UNSUPPORTED` | Contract/provider-config/catalog version is malformed or unsupported. |
| `PCP_SCHEMA_INVALID` | Wrong JSON type, missing required field, or invalid scalar. |
| `PCP_SCHEMA_UNKNOWN` | Unknown structural field. |
| `PCP_IDENTITY_INVALID` | Invalid/duplicate project, provider, operation, or artifact identity. |
| `PCP_DIGEST_INVALID` | Digest is malformed or does not match canonical desired bytes. |
| `PCP_PROVENANCE_INVALID` | Desired leaf provenance is missing, duplicate, unsorted, or malformed. |
| `PCP_PROVIDER_SET_MISMATCH` | Desired and provider-row sets differ or rows are unsorted. |
| `PCP_APPLY_INVALID` | Last-applied evidence is incomplete or mismatched. |
| `PCP_OBSERVATION_INVALID` | Observation/freshness/security/capability/artifact evidence is invalid. |
| `PCP_DIAGNOSTIC_INVALID` | Diagnostic envelope/order/code is invalid. |
| `PCP_STATUS_UNKNOWN` | Provider or aggregate status literal is unknown. |
| `PCP_STATUS_INCONSISTENT` | Provider status does not equal the deterministic derivation. |
| `PCP_AGGREGATE_MISMATCH` | Aggregate IDs/status map/result do not match provider rows. |
| `PCP_PARTIAL_RESULT` | Error diagnostics coexist with a result, or failure has no error diagnostic. |

## Versioning and upgrade

A v1.0 reader accepts only `1.0.x` envelope/config versions and the catalog version class it
explicitly supports. It rejects unknown minor/major versions, fields, identities, and enum
values; it MUST NOT strip unknowns, guess from shape, or retry as legacy.

- **major:** changes ownership, envelope shape, identity/digest semantics, status/aggregate
  meaning or precedence, no-partial-result behavior, or removes/renames a frozen field/code;
- **minor:** adds an optional understood field or status/diagnostic that old readers can safely
  reject without changing existing results;
- **patch:** editorial clarification or additional fixtures with identical accepted/rejected
  behavior.

An upgrade is keyed by the exact recognized source version, produces one complete current
snapshot, and commits it only with no error diagnostics. Unknown/ambiguous source versions,
incomplete target snapshots, or upgrade errors preserve the prior record and return no partial
new result. Backup/rollback authorization remains outside this read contract.

## Legacy source classes and admission

Migration is a closed consumer of the desired/status model; it does not become a new source of
provider intent. A source is admitted only when its class, version, complete P0 classification,
ownership evidence, artifact set, provider set and preimages are all explicit. Shape inference,
mtime ordering, basename matching, rendered-output adoption and best-effort partial plans are
forbidden.

| Source class | Accepted version | Required evidence | Outcome |
|:--|:--|:--|:--|
| `legacy-absent-config` | exact synthetic `0` | provider config is absent; no candidate artifact or override exists | in-memory Claude-only compatibility: Claude Code selected, Codex not selected, no carrier/target/lock/status/backup write |
| `provider-config-v1` | `1.0.x` only | complete current desired snapshot; every artifact has one P0 classification, managed ownership proof, target/preimage/postimage and backup identity | a complete `plan`/`check`/`dry-run`, or an Owner-authorized atomic `apply` |

`canonical-equivalent`, `stale-managed-copy`, and `broken-link` are the only recognized
actionable P0 classifications. A broken link remains actionable only when the recorded artifact
identity and ownership evidence prove its exact managed target; absence alone proves nothing.
`local-override` and `ambiguous` always refuse. An unowned target, incomplete classification,
corrupt source, missing/duplicate provider row, changed preimage, unknown class/version or
newer major refuses before backup or write. A refusal never falls back to legacy, strips unknown
fields, adopts bytes, or silently enables Codex.

The complete target snapshot is validated before an apply is authorized. It contains the exact
desired digest and every selected provider row; partial provider snapshots are invalid. Missing
provider config is compatibility input, not an implicit migration request.

## Migration transaction

`plan`, `check`, and `dry-run` are byte-preserving. They may return `MIG_PLAN_READY` or
`MIG_COMPATIBILITY_NOOP`, but MUST NOT create a backup, target, lock, status record, config key or
approval. The checker is also no-write and proves contract/fixture shape only; it never performs a
provider or fleet operation.

`apply` requires a separate accepted immutable decision bound to the exact action digest. The
P1.3 contract-freeze decision approves contract bytes only and is never apply authority. After
authorization, one transaction executes in this order:

1. revalidate class/version, complete classification and ownership, exact provider/action sets,
   target snapshot, decision digest, every current preimage and the exact backup inventory;
2. capture recoverable source bytes for every declared managed artifact before its first write;
3. stage and validate every selected provider result without publishing partial success;
4. publish provider targets, then the provider artifact lock, then provider-qualified status;
5. read back the exact target/lock/status snapshot and run the same reconcile a second time;
6. report `MIG_APPLIED` only when readback matches and the second reconcile action set is empty.

The write order is closed: `provider-targets` → `provider-lock` → `provider-status`. A status row
cannot precede its lock/target commit. One provider's success never masks a failed, missing,
unsupported, untrusted or stale peer. An uncommitted or partially published snapshot is failure,
not last-applied evidence and not health evidence.

## Rollback and convergence

Any provider failure, write interruption, readback mismatch or non-empty second reconcile keeps
the aggregate non-green. Rollback restores only the transaction's declared managed targets,
lock and status from the captured preimage set; it neither deletes nor overwrites unowned bytes,
local overrides, ambiguous targets, provider config, credentials, Brain state, fleet roots or
other provider outputs. Rollback revalidates the same ownership and backup identities before each
restore. Incomplete rollback reports `MIG_ROLLBACK_FAILED` and preserves all recoverable evidence.

A restored partial-provider transaction reports `MIG_PROVIDER_PARTIAL`; a readback mismatch
reports `MIG_READBACK_FAILED`; a non-empty second reconcile reports
`MIG_SECOND_RECONCILE_NONEMPTY`. None may be downgraded to a warning or `ready`. Health may become
green only after a committed complete snapshot, matching readback and an empty second reconcile.

### Stable migration action and refusal codes

| Code | Closed meaning |
|:--|:--|
| `MIG_COMPATIBILITY_NOOP` | Provider config is absent; preserve the in-memory Claude-only default and write nothing. |
| `MIG_PLAN_READY` | A recognized, complete no-write plan/check/dry-run candidate is ready for separate apply authorization. |
| `MIG_APPLIED` | Exact authorized transaction committed, read back and reconciled to an empty second action set. |
| `MIG_SOURCE_CLASS_UNKNOWN` | Source class is not recognized. |
| `MIG_SOURCE_NEWER_MAJOR` | Source declares a newer major and has no compatibility fallback. |
| `MIG_SOURCE_VERSION_UNSUPPORTED` | Source version is malformed or outside the exact supported class. |
| `MIG_SOURCE_CORRUPT` | Source or transaction shape is malformed/inconsistent. |
| `MIG_CLASSIFICATION_INCOMPLETE` | P0 classification is not complete for the exact artifact set. |
| `MIG_CLASSIFICATION_AMBIGUOUS` | At least one target remains ambiguous. |
| `MIG_LOCAL_OVERRIDE` | A project-owned local override blocks automatic migration. |
| `MIG_OWNERSHIP_UNPROVEN` | Managed ownership evidence is absent or does not bind the target. |
| `MIG_PREIMAGE_CHANGED` | A target changed after planning; refuse before backup/write. |
| `MIG_TARGET_SNAPSHOT_INCOMPLETE` | The proposed current snapshot is partial. |
| `MIG_TARGET_SNAPSHOT_INVALID` | The complete proposed snapshot fails validation. |
| `MIG_PROVIDER_SET_MISMATCH` | Desired, artifact and provider result sets are not exact. |
| `MIG_WRITE_FORBIDDEN` | A plan/check/dry-run attempted to write or claim authority. |
| `MIG_AUTHORITY_REQUIRED` | Apply lacks an accepted exact action decision. |
| `MIG_BACKUP_SET_MISMATCH` | Recoverable backup inventory is not the exact managed artifact set. |
| `MIG_PROVIDER_PARTIAL` | A provider failed; the declared transaction was restored. |
| `MIG_ROLLBACK_FAILED` | Exact rollback did not restore the declared preimage. |
| `MIG_READBACK_FAILED` | Published target/lock/status bytes do not match the committed plan. |
| `MIG_SECOND_RECONCILE_NONEMPTY` | Idempotence proof found another action after apply. |

## Exact G01-G11 predecessor crosswalk

The source-row digest is SHA-256 of compact sorted-key UTF-8 JSON containing every cell of the
corresponding frozen predecessor `## Preconditions` row. The checker recomputes it from archived
bytes. G01–G11 MUST NOT be weakened, skipped, reordered or inferred from a later green result.

| Gate | Source row SHA-256 | Preserved obligation | P1.3 enforcement |
|:--|:--|:--|:--|
| G01 | sha256:192d725d992b7aa0565766c7994a42b8d139228970515a72bb2ab2d9c7317c8c | frozen P0 contracts, accepted ADR, terminal items, independent GREEN and protected delta | P1.3 admits only terminal P0 evidence and never repairs or rewrites P0 |
| G02 | sha256:08c041ad682a0715f2a43597c4684377506df8adadd0c025a107884ac937c178 | frozen provider config, compatibility/no-write evidence and independent P1 audit | P1.3 supplies migration/rollback evidence; P2 remains closed until the P1 audit |
| G03 | sha256:861f5f9314ec57eff3ad987c0ed3c0ab4e0631dbbddce933b9e8638ccbc81070 | provider publication parity and independent verification | migration never treats rendered publication output as canonical source |
| G04 | sha256:75114032944a0621ecf6fa028c11d45c6b23fc47236d4440cc94cc58550b844b | stable command identity, provider-native invocation and fail-closed routing | migration carries no command downgrade or cross-provider invocation fallback |
| G05 | sha256:c12459f83ba54a7cccb0394442c17a5ce65d76bfdb041dc8e98db926daa2934c | harness/instruction compatibility, security-axis separation and protected delta | apply authority remains separate from trust, approval policy and sandbox |
| G06 | sha256:691033e9c9d031a0973c9bf243e526aa34c13e87c9c4b8cd933e3a3e170e56ec | committed cold checkpoint and both-provider evidence | partial/uncommitted provider state cannot satisfy readback or convergence |
| G07 | sha256:9a13a25b9727678c49e3b3d86df4c28b86d42725bde6b0afc51054cf238f5c72 | exact provider docs/catalog hashes and explicit full access | this contract adds no default access and no documentation shortcut |
| G08 | sha256:1a3fa32120bc8125ba5a0361930261a0e09856d5b2fe86f6a0c63d3059864930 | isolated proof, exact live approval, rollback and idempotence | exact decision digest, backup, readback and second-noop are mandatory |
| G09 | sha256:5c31b4059dceb9a281323c10b7cd41e109c9939612caa8d6ec330abdddebdc8b | ownership/replacement/rollback evidence before cleanup | unowned, local-override and ambiguous assets refuse; no cleanup is authorized |
| G10 | sha256:660c4b43df91adfa40d6f4ffab04be028f964242297a0a9abce7c33cb37b800e | final GREEN, Owner approval, clean release scope and FOREMAN no-write | P1.3 has no FOREMAN mutation or release-opening authority |
| G11 | sha256:60cdaff8993cdd7f82fb6903804f96e0d86e7ba1aee76c62969f2751ead28233 | fleet no-write and separate future rollout-plan authority | contract fixtures are plan-local; no fleet/project operation is performed |

## Approved Owner decision set C1-C6

The Owner decision is atomic and freezes the exact candidate together:

- **C1 — identity/schema:** v1.0.0 envelope, desired/last-applied/observed identities,
  deterministic digests and no-partial result;
- **C2 — SSOT composition/ownership:** provider config, capability manifest, artifact lock,
  canonical Skill Core and provider-scoped adapter evidence retain their existing owners;
- **C3 — negotiation/parity:** ordered fail-closed capability negotiation, provider-qualified
  support labels and third-provider additive registration;
- **C4 — status/diagnostics:** provider/aggregate precedence, independent provider rows and stable
  schema/migration diagnostics;
- **C5 — migration/rollback:** recognized source table, exact transaction/write order, ownership,
  preimage, backup, rollback, readback, second-noop and G01–G11 no-weaken crosswalk;
- **C6 — compatibility/authority:** absent config remains no-write Claude-only compatibility;
  contract freeze does not authorize apply, provider, package, Brain, credential or fleet writes.

Exact approval reply:

```text
APPROVE P1.3 PROVIDER-CONTROL-PLANE C1-C6 AS WRITTEN
```

Any C1–C6 change is a revision request, not partial approval. Only the accepted immutable Owner
reply may replace `pending exact Owner decision`, set `Status: frozen` and complete the v1.0.0
freeze bookkeeping.

## Normative fixtures and validation

`schema-positive.json` contains complete successful envelopes. `schema-negative.json`
contains one JSON-pointer mutation per case, its positive base ID, and the exact refusal code.
The stdlib checker MUST prove every positive case is accepted, every declared negative mutation
is rejected by exactly its declared code, desired digests are recomputed, provider/aggregate
status is re-derived, and the contract carries every closed literal above.

The checker and fixtures are authored from this contract. They MUST NOT import package runtime
objects, regenerate expectations from current serializers, special-case a fixture digest, write
outside their paths, or mutate provider/config/artifact carriers.

The ownership stage additionally validates the exact carrier inventory, Skill Core neutrality,
additive adapter boundary, deterministic negotiation order, selected-provider aggregation, and the
synthetic third-provider registration. Its negative cases change one invariant each. The generated
ownership Markdown MUST be byte-identical to a fresh projection from the JSON matrix.
