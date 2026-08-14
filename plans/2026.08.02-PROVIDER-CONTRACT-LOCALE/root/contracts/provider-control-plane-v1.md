# Provider control-plane contract

**Version:** v1.0.0-draft
**Status:** draft
**Owner:** repository owner
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

## Normative fixtures and validation

`schema-positive.json` contains complete successful envelopes. `schema-negative.json`
contains one JSON-pointer mutation per case, its positive base ID, and the exact refusal code.
The stdlib checker MUST prove every positive case is accepted, every declared negative mutation
is rejected by exactly its declared code, desired digests are recomputed, provider/aggregate
status is re-derived, and the contract carries every closed literal above.

The checker and fixtures are authored from this contract. They MUST NOT import package runtime
objects, regenerate expectations from current serializers, special-case a fixture digest, write
outside their paths, or mutate provider/config/artifact carriers.
