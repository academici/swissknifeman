# Provider health composition contract

**Version:** v1.0.0
**Status:** frozen
**Owner:** root provider-health composition boundary
**Approval:** P6.2

## Purpose

`provider-health-v1` is a pure composition contract over immutable results from their owners. It
does not read provider targets, configuration carriers, credentials, raw command output, or
another package's private Python API. It does not recalculate token budgets, capability levels,
locale fallback, migration state, trust, settings, or adapter readback. Check and aggregation are
strictly no-write and never authorize repair.

The contract keeps desired intent separate from observation. Absence, `not-selected`,
`not-required`, `unsupported`, `unavailable`, `unresolved`, `unknown`, `stale`, and `error` remain
distinct. One green provider or project never masks a required non-green peer.

Normative words `MUST`, `MUST NOT`, `SHOULD`, and `MAY` are literal.

## Stable identities and redaction

Projects use sealed non-secret project IDs. Provider IDs and axis IDs use the open dotted identity
grammar `^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*$`; no Claude/Codex enum ceiling exists. Evidence
and source IDs are opaque, non-secret identities. Absolute roots, credentials, tokens, environment
values, raw provider payloads, and secret-like names MUST NOT enter a result.

Every digest is `sha256:<64 lowercase hex>` over UTF-8 canonical JSON with sorted object keys,
separators `,` and `:`, and unescaped Unicode. Input ordering does not affect row, diagnostic,
project, or fleet ordering.

## Project evaluation input

A project evaluation consumes an exact set of desired requirements and owner-produced evidence at
one explicit UTC `evaluated_at` timestamp.

A requirement has exactly:

| Field | Meaning |
|:--|:--|
| `provider_id` | Desired provider identity. |
| `axis_id` | Stable capability or health-axis identity. |
| `selected` | Desired provider selection, never inferred from output. |
| `required` | Whether this selected provider/axis must pass. |

`required=true` with `selected=false` is contradictory and rejected. Requirement keys are
`provider_id × axis_id`; duplicates remain non-green and are never merged.

Evidence has exactly:

| Field | Meaning |
|:--|:--|
| `provider_id`, `axis_id` | Exact requirement key. |
| `state` | Owner result: `pass`, `not-selected`, `not-required`, `unsupported`, `unavailable`, `unresolved`, `unknown`, or `error`. |
| `evidence_id`, `source_id` | Redacted immutable identities, not values or paths. |
| `observed_at`, `expires_at` | UTC RFC 3339 `...Z`; expiry is strictly after observation. |

The compositor MUST NOT reinterpret owner evidence. It may only check exact coverage, identity,
freshness, desired legality, ordering, and aggregate semantics.

## Project result and legality

The result has exactly `contract_version`, `project_id`, `evaluated_at`, `rows`, `diagnostics`,
`aggregate`, and `result_digest`. Rows are sorted by provider and axis. A row repeats the four
requirement fields, carries the evidence identity/timestamps when present, and adds derived
`status` and `healthy`.

The derived row status is the evidence state, except:

- absent evidence is `missing`;
- duplicate requirement or evidence is `duplicate`;
- evidence with `expires_at <= evaluated_at` is `stale`.

A selected required row is healthy only as `pass`. A selected optional row is healthy as `pass`,
`not-required`, or `unsupported`. A provider that desired intent did not select is healthy only as
`not-selected`. Therefore required unsupported, unavailable, unresolved, unknown, stale, missing,
duplicate, or error rows are always non-green. An extra evidence key is non-green and is never
silently discarded as success.

Project aggregate is exactly `green` or `non-green`. It is `green` only when the requirement set is
non-empty, every exact row is healthy, and there are no diagnostics. All other complete reports are
`non-green`; producing a correct non-green report is still successful execution of the evaluator.

## Fleet exact-set aggregate

Fleet input names the non-empty sealed exact project-ID set and supplies complete project results
from one evaluation boundary. Missing, extra, or duplicate project rows remain distinct stable
diagnostics. Projects sort by sealed project ID.

Fleet aggregate is `green` only when observed project IDs equal the sealed set exactly, every
project occurs once, every project aggregate is `green`, and the fleet diagnostic set is empty.
Otherwise it is `non-green`. A live graph, locator result, successful subset, or one provider's
success cannot change fleet membership or mask a peer.

## Package-owned evidence

- Skiller owns selection, transitive dependency closure, channels, and provider-qualified skill
  measurements/budget policy.
- Harness owns provider trust, security profile, settings readers, and environment checks.
- Provider adapters/P3 own desired-versus-observed status and readback.
- P4 owns locale/source acceptance; P5 owns migration/unresolved outcomes.
- mAInd owns public-CLI orchestration, timeouts/schema admission, sealed project iteration, and the
  final operational report.

mAInd invokes worktree-local package CLIs with bounded timeouts. Non-zero exit, timeout, malformed
JSON, schema mismatch, or unreadable evidence becomes an explicit evidence row; it is never skipped
or retried through another provider. mAInd MUST NOT import Skiller or Harness internals.

Provider-qualified skill measurements remain Skiller-owned. Each row names provider, exactly one
model or model-family identity, surface (`listing`, `loaded-body`, or `runtime`), numeric value when
known, unit, method, uncertainty, measurement class, `observed_at`, `expires_at`, and source ID.
Exact, estimate, lower-bound, upper-bound, and unknown classes remain distinct. Thresholds belong to
provider/surface policy. Incompatible units/classes are never added into one scalar verdict;
unknown or stale required measurements remain visible and non-green. Repeated dependency/budget
diagnostics aggregate only by stable code plus a sorted affected-identity set.

## Stable diagnostics

Diagnostics use the existing provider status shape: `severity`, `code`, `message`, and
`source_ref`, ordered by severity, source, then code. The compositor emits:

| Code | Meaning |
|:--|:--|
| `PH_PROJECT_ID_INVALID` | Project identity is invalid or unsafe. |
| `PH_PROVIDER_ID_INVALID`, `PH_AXIS_ID_INVALID` | Provider or axis identity is invalid. |
| `PH_REQUIRED_PROVIDER_NOT_SELECTED` | Desired requirement contradicts selection. |
| `PH_REDACTION_REQUIRED` | An evidence/source identity is unsafe. |
| `PH_TIMESTAMP_INVALID`, `PH_FRESHNESS_INVALID` | Evidence time is malformed or impossible. |
| `PH_DUPLICATE_REQUIREMENT` | A requirement key repeats. |
| `PH_EVIDENCE_MISSING`, `PH_EVIDENCE_DUPLICATE`, `PH_EVIDENCE_EXTRA` | Evidence set is not exact. |
| `PH_EVIDENCE_STALE` | Required current evidence expired. |
| `PH_REQUIRED_UNSUPPORTED` | Desired required capability is unsupported. |
| `PH_SELECTION_MISMATCH`, `PH_REQUIREMENT_MISMATCH` | Owner state contradicts desired intent. |
| `PH_AXIS_NON_GREEN` | A row is unavailable, unresolved, unknown, or error. |
| `PH_PROJECT_MISSING`, `PH_PROJECT_DUPLICATE`, `PH_PROJECT_EXTRA` | Fleet membership is not exact. |

## Versioning

A v1 reader accepts only the exact frozen schema. Unknown fields, identities, states, versions, or
partial results fail closed.

- **major:** changes ownership, requirement/evidence/result shape, legality, freshness, exact-set,
  redaction, or aggregate meaning;
- **minor:** adds an optional understood field that old readers can safely reject;
- **patch:** editorial clarification or additional fixtures with identical behavior.
