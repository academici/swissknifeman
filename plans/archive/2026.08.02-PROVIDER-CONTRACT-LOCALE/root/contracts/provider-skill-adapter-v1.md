# Provider Skill Adapter contract

**Version:** v1.0.0-draft
**Status:** draft
**Owner:** provider adapter packages
**Consumes:** Skill Core v1 and provider capability catalog v1

## Purpose

A Provider Skill Adapter is an additive projection over one immutable Skill Core. It maps shared
meaning into one provider's discovery, invocation, target layout, capability, measurement, replay,
and diagnostics without creating provider branches in the Skill Core or reading another provider's
output.

Normative words `MUST`, `MUST NOT`, `SHOULD`, and `MAY` are literal.

## Registration record

Each descriptor has exactly:

| Field | Contract |
|:--|:--|
| `contract_version` | Supported `1.0.x` adapter contract version. |
| `adapter_id` | Stable lowercase dotted adapter identity. |
| `adapter_version` | Adapter SemVer. |
| `provider_id` | Stable ID matching the capability manifest; validated by syntax and manifest membership, never a shared Claude/Codex enum. |
| `skill_id` | Exact Skill Core identity. |
| `required_capabilities` | Ordered required capability requirements. |
| `optional_capabilities` | Ordered optional capability requirements. |
| `native_extensions` | Ordered provider-owned Native Extension IDs, separate from common capabilities. |
| `discovery` | Provider-owned discovery mapping and listing budget. |
| `renderer` | Deterministic renderer identity/version and owned target roots. |
| `invocation` | Mapping of shared invocation intent or an explicit unsupported result. |
| `measurement` | Typed provider-qualified meter with unit/method/bounds/version. |
| `replay` | Provider-qualified executable scenarios and unavailable/skip semantics. |
| `status_namespace` | Exact provider-scoped status/evidence identity. |

`skill_id` MUST resolve to a validated Skill Core record and every required or optional Capability
ID MUST resolve in the validated capability manifest. The descriptor Capability contract MUST
equal that Skill Core's complete contract: no removal, required-to-optional downgrade, accepted
level narrowing/reordering, or substitution with another catalog Capability is additive. Each seam is a closed minimal record:
`discovery={unit,budget_unit,degradation}`,
`renderer={id,version,target_roots}`,
`invocation={mode,unsupported}`,
`measurement={unit,method,bounds,version}`, and
`replay={fixture_set,unavailable}`. IDs, SemVer values, booleans, non-empty strings, and relative
target roots retain their declared types; a non-empty but vacuous mapping is not conformance.
Every seam string is strip-nonempty; whitespace is not a value.

All Capability, Native Extension and other dotted semantic identities use the frozen core grammar
`^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*$`; colon and underscore are invalid. Provider IDs are
validated separately against the adapter-registration provider grammar. Every human string and
list item in the descriptor is strip-nonempty, and contract-declared unique lists reject repeats.
`skill_id` is the separate frozen `<bucket>/<frontmatter-name>` identity and is reused byte-for-byte
from Skill Core; adapters never translate it.

Adding provider C means adding one descriptor plus its provider-owned renderer, invocation,
measurement and replay carriers. The registration schema has no provider enum. Existing adapters
and the Skill Core remain byte-unchanged unless shared meaning changes through a separate contract
decision.

## Additive semantic rule

The adapter output MUST preserve the exact Skill Core identity, job, positive/negative/explicit
trigger boundary, inputs, outputs, invariants, capabilities, workflow, resources, and provenance.
Provider-native metadata MAY only be additive. A descriptor or render plan containing
`semantic_replacement`, `job_override`, `trigger_override`, `invariant_override`, or a provider
copy of the whole semantic record is `ADAPTER_SEMANTIC_REPLACEMENT`. This recursive prohibition
also covers nested `semantic_copy`, `core`, `skill_core`, `job`, `trigger`, `invariants`, and
`outputs` keys at any depth inside a descriptor or seam.

The adapter reads only canonical inputs, the frozen capability manifest, effective selection with
leaf provenance, its own descriptor, and its own managed observation/lock. It MUST NOT read or
write another provider's target, lock, evidence, status, measurement, replay result, or diagnostic.
Rendered output, stale lock, observed bytes, and human diagnostics are never semantic inputs.

## Capability negotiation

Negotiation consumes exactly one validated full capability manifest, the complete P1.1
`DesiredSnapshot` selection map with leaf provenance, and one descriptor whose `provider_id`
matches the selected row. Every ready or blocked result repeats that exact `provider_id` so all
limitations, extensions, labels, and diagnostics remain provider-qualified. Explicit capability
decisions take precedence over catalog support: explicit `false` denies even a native capability;
explicit `true` or missing decision continues to the manifest support record.

Required requirements are evaluated by capability ID and fail before render in this exact order:

1. `NEG_PROVIDER_DISABLED`;
2. `NEG_PROVIDER_MISMATCH`;
3. `NEG_REQUIRED_DENIED`;
4. `NEG_REQUIRED_MISSING`;
5. `NEG_REQUIRED_UNSUPPORTED`;
6. `NEG_REQUIRED_LEVEL_REJECTED`;
7. `NEG_NATIVE_EXTENSION_INVALID`.

Within one code, capability or extension IDs sort lexicographically. All required failures are
returned in that order and the outcome is `blocked`; no managed bytes or partial render plan is
returned. Optional denied, missing, unsupported, or level-rejected requirements remain explicit
provider-qualified limitations and do not borrow support from another provider.

Native Extensions are evaluated only after common required capabilities. They stay provider-owned,
must use the exact descriptor provider namespace and never enter the common capability matrix.

## Provider-qualified presentation

`native`, `adapted`, and `unsupported` remain the only Support Levels. Human words are derived
labels, not a rival enum:

- `supported` means the provider's required common capabilities negotiated without a blocker;
- `degraded` is additionally shown when a satisfied provider uses adapted support, has catalog
  limitations, or has any optional limitation;
- `exclusive` is additionally shown only when an enabled provider-owned Native Extension exists.

Labels are computed per provider, retain the underlying levels/limitations/extensions, and never
enter the capability manifest. Aggregate presentation is non-green when any selected provider is
blocked; a ready peer cannot mask it.

## Ownership and writes

The exact machine source is `artifacts/P1-provider-ownership-capability-matrix.json`. Its Markdown
file is a generated byte-stable projection. The matrix assigns one owner and explicit read, write,
derived-from, and forbidden-use sets to every declared carrier family.

An adapter may write only a matching provider projection plan, matching managed target boundary,
matching provider evidence/status, and the matching lock through the artifact transaction. Check,
negotiate, render-plan, audit, and self-test are no-write. A lock or target owned by a different
provider is a refusal, never a conversion source.

## Third-provider conformance and versioning

`third-provider.json` is normative: its supplied synthetic manifest owns the provider, required
Capabilities and Native Extensions while the shared real manifest remains unchanged. The provider
registers all five required seams —
`discovery`, `renderer`, `invocation`, `measurement`, and `replay` — without adding a shared provider
enum, editing the Skill Core, or editing Claude/Codex adapters.

- **major:** changes additive semantics, required seams, negotiation/failure ordering, ownership,
  cross-provider isolation, or support-label meaning;
- **minor:** adds an optional descriptor field or a provider registration old readers safely reject;
- **patch:** evidence/diagnostic/fixture clarification with identical behavior.

Unknown fields or versions, duplicate/unowned carriers, provider enum ceilings, cross-provider
read/write, output-as-source, unsupported required capabilities, missing selected-provider rows,
and partial-provider masking fail closed with stable codes.
