# Provider configuration contract

**Version:** v1.0.0
**Status:** frozen
**Approval Owner:** Dmitry Vostrikov
**Approval:** D70, 2026-07-20
**Inputs:** frozen D53 vocabulary/scenarios, D55 capability/artifact contracts, D59 migration gates, D13 precedence

## Purpose

This contract defines the provider-selection input shared by `skiller`, `maind`, and
downstream provider adapters. It gives project and fleet configuration one schema, one
precedence order, one field-by-field merge algorithm, and one diagnostic/provenance model
without moving file ownership or I/O into `core`.

The contract selects Provider, Capability, and Native Extension identities already owned by
the frozen capability contract. It does not define Support Level, provider bindings, artifact
paths, model routing, credentials, Project Trust, Approval Policy, Sandbox Boundary, or
provider-specific renderer options. It authorizes no write to a carrier or provider output.

Normative words `MUST`, `MUST NOT`, `SHOULD`, and `MAY` are literal. D70 froze this
contract as the mandatory provider-configuration input for downstream implementation.

## Inputs and carriers

Every explicit carrier contributes at most one `ProviderConfigLayer`. File ownership remains
where it is today; the pure resolver receives already-parsed layers plus source descriptors.

| Rank | Layer ID | Carrier and JSON Pointer | Owner | Presence and write rule |
|:--|:--|:--|:--|:--|
| 1 | `operation` | in-memory operation argument, root pointer `/` | calling command/API | Optional, invocation-local, never persisted by the resolver. Caller MUST supply a stable operation ID. |
| 2 | `project` | `.swissknife.json#/providers` | project / `skiller` schema | Optional. Project-owned declaration; fleet state cannot rewrite or outrank it. |
| 3 | `fleet-project` | exact target match at `config.json#/projects/<index>/providers` | `maind` fleet config | Optional. Exactly zero or one project record may match the canonical project ID. |
| 4 | `fleet-defaults` | `config.json#/providers/defaults` | `maind` fleet config | Optional shared default for projects resolved through that fleet config. |
| 5 | `legacy` | synthetic layer; no file and no JSON Pointer | this compatibility contract | Always available as the lowest layer; never written to disk. |

`config.json#/providers` is a fleet envelope whose only v1 key is `defaults`. The value of
`defaults`, each `projects[].providers`, `.swissknife.json#/providers`, and the operation
argument all use the same layer schema below. A carrier is absent when its owning key is
absent; `{}`, `null`, or an empty `selection` is invalid rather than another spelling of
absence.

Source descriptors are resolver inputs, not user-overridable config fields:

```json
{
  "kind": "operation|project|fleet-project|fleet-defaults|legacy",
  "id": "stable non-secret identity within this resolution",
  "carrier": "operation|.swissknife.json|config.json|legacy",
  "path": "/RFC6901/pointer/to/layer"
}
```

The IDs are respectively `operation:<operation-id>`, `project:<project-id-or-local>`,
`fleet-project:<project-id>`, `fleet-defaults:config`, and
`legacy:claude-code-compat`. Absolute host paths, credentials, tokens, environment values,
and rendered output MUST NOT enter the source descriptor.

## Normative schema

### ProviderConfigLayer

```json
{
  "contract_version": "1.0.0",
  "selection": {
    "claude-code": {
      "enabled": true,
      "capabilities": {
        "instructions.project": true
      },
      "native_extensions": {
        "claude-code.fixture-native": false
      }
    },
    "codex": {
      "enabled": false
    }
  }
}
```

A layer is a JSON object with exactly these keys:

| Field | Cardinality | Rule |
|:--|:--|:--|
| `contract_version` | required once | SemVer of this input contract. v1 readers apply the Versioning rules below. |
| `selection` | required, non-empty object | Map keyed by stable Provider ID from the supplied capability manifest. |

Each `selection.<provider-id>` value is a non-empty `ProviderSelection` object with only:

| Field | Type | Meaning |
|:--|:--|:--|
| `enabled` | boolean, optional | `true` selects the Provider; `false` explicitly disables it. Missing inherits a lower layer. |
| `capabilities` | non-empty object of boolean values, optional | Map keyed by frozen Capability ID. `true` explicitly permits/requests it; `false` explicitly denies it; missing makes no config-level decision. |
| `native_extensions` | non-empty object of boolean values, optional | Map keyed by Native Extension ID owned by this Provider. `true` opts in; `false` opts out; absence across all explicit layers is disabled by default. |

The only Provider IDs in v1 are `claude-code` and `codex`. Aliases such as `claude`,
`chatgpt`, model names, CLI names, display names, and case variants are invalid. Capability
and Native Extension IDs MUST resolve in the supplied frozen capability manifest. A Native
Extension ID MUST start with `<provider-id>.` and its manifest `provider_id` MUST equal the
containing Provider ID.

The booleans above are selection constraints, not Support Levels. For an enabled Provider,
`capabilities.<id> = true` config-enables the Capability and forces resolution-time Support
Level validation; it does not render an artifact by itself. `false` blocks any Adapter that
requires the Capability. Missing capability selection is unconstrained: it does not mean
disabled, enabled, or unsupported, and a requesting Adapter still declares its requirement
and accepted Support Levels under the capability contract. Explicit `true` is valid only
when Support Level is `native` or `adapted`; `unsupported` is an error. A disabled Provider
is inactive regardless of retained capability/extension selections; retaining those values
is valid and does not silently enable it.

Native Extensions have no config `options` field in v1. Their provider-native binding owns
syntax elsewhere. Adding opaque option bags here would create an unversioned special case and
is forbidden.

### EffectiveProviderConfig

On success the pure resolver returns:

```json
{
  "contract_version": "1.0.0",
  "catalog_version": "<observed capability catalog SemVer>",
  "selection": {
    "claude-code": {
      "enabled": true,
      "capabilities": {},
      "native_extensions": {}
    },
    "codex": {
      "enabled": false,
      "capabilities": {},
      "native_extensions": {}
    }
  },
  "provenance": [],
  "diagnostics": []
}
```

`selection` contains every Provider in the supplied catalog. `enabled` is always materialized.
`capabilities` and `native_extensions` contain only keys explicitly selected by an input
layer; absent Native Extensions are nevertheless inactive by normative default. Consumers
MUST check `enabled` before either map. `catalog_version` is observed provenance and is not
configurable by a layer.

Any error diagnostic returns no effective config (`effective = null`) and causes every
dependent plan/check/apply operation to fail before write. A resolver MAY return validated
layers with the errors for debugging, but MUST NOT return a partial effective selection.

## Precedence and merge

Exact precedence, strongest to weakest, is: `operation > project > fleet project > fleet defaults > legacy`.
Implementations resolve deterministically from legacy upward, while diagnostics and operator
documentation display the stronger-first order above.

There is no generic recursive object merge. The only merge operations are these:

| Field/boundary | Rule | Missing value | Explicit `false` | `null` / deletion marker |
|:--|:--|:--|:--|:--|
| `contract_version` | Validate independently per explicit layer; never merge. | Error inside a present layer. | Not applicable. | Error. |
| `selection` | Merge map by exact Provider ID. Higher layer preserves unrelated Provider IDs. | Inherit the whole lower map. | Not applicable. | Error. |
| `selection.<provider>.enabled` | Highest-ranked defined boolean replaces lower boolean. | Inherit lower value. | Replaces lower `true`. | Error. |
| `selection.<provider>.capabilities` | Merge map by exact Capability ID. | Inherit unrelated/lower IDs. | Replaces lower `true` for that ID only. | Error. |
| `selection.<provider>.native_extensions` | Merge map by exact Native Extension ID. | Inherit unrelated/lower IDs. | Replaces lower `true` for that ID only. | Error. |

The synthetic legacy layer initializes every catalog Provider with `enabled = false`, then
sets `claude-code.enabled = true`. It supplies no capability or Native Extension selections.
These values carry `explicit = false` provenance, so missing remains distinguishable from an
explicit disable. New Providers added to a later catalog therefore remain disabled by default.

Each rank accepts zero or one layer. Two operation layers, two matched fleet project records,
or any other same-rank candidates are ambiguity errors; array order, file order, timestamp,
or caller order MUST NOT select a winner. An unmatched fleet project record is not an input.
Project-local config always outranks matched fleet state, including explicit `false`.

## Compatibility

When `providers` is absent from the project, its matched fleet record, fleet defaults, and the
operation input, resolution produces the prior Claude Code-only result:

- `claude-code.enabled = true` with source `legacy:claude-code-compat`;
- `codex.enabled = false` with the same compatibility source;
- no explicit capability constraints or Native Extensions;
- diagnostic `PCFG_LEGACY_DEFAULT_APPLIED` and no filesystem write.

This is an in-memory result. The resolver and every read/check/doctor path MUST preserve the
carrier bytes and MUST NOT add `providers`, enable Codex, migrate `agent: "claude"`, or create
provider artifacts. Existing non-provider keys keep their current package-owned semantics and
are outside this contract.

If any explicit layer exists, the same synthetic base still supplies otherwise-missing
Provider `enabled` values; the provenance record makes that fallback visible. Missing is never
converted to an explicit disable, and a fleet layer cannot be persisted into project config.
An intentionally all-disabled effective selection is valid; a later operation requiring a
Provider fails before render.

## Provenance

Provenance is leaf-granular and deterministic. Each winning effective field has exactly one
record:

```json
{
  "effective_path": "/selection/codex/enabled",
  "source": {
    "kind": "fleet-project",
    "id": "fleet-project:demo",
    "carrier": "config.json",
    "path": "/projects/3/providers"
  },
  "source_path": "/projects/3/providers/selection/codex/enabled",
  "explicit": true
}
```

Records are sorted lexicographically by `effective_path`. Map containers do not receive a
synthetic winner: their leaves retain independent provenance. A higher layer that changes one
Capability cannot claim provenance for preserved siblings. Legacy `enabled` records use
`explicit = false`; all file/operation values use `explicit = true`.

The resolver also records the observed config contract versions and capability catalog
version once per resolution. Provenance contains identity and JSON Pointers, not source file
content, absolute paths, secrets, credentials, provider outputs, timestamps, or host state.

## Diagnostics

Every diagnostic has this exact envelope:

```json
{
  "severity": "error|warning|info",
  "code": "PCFG_STABLE_CODE",
  "message": "human-readable non-stable text",
  "path": "/RFC6901/pointer/in/source",
  "source": {
    "kind": "project",
    "id": "project:demo",
    "carrier": ".swissknife.json",
    "path": "/providers"
  }
}
```

`severity`, `code`, `path`, and `source` are mandatory. Package adapters MAY localize
`message` but MUST preserve those four fields. Diagnostics are ordered by severity
(`error`, `warning`, `info`), then source rank (operation through legacy), `source.id`,
`path`, and `code`.

| Code | Severity | Condition and effect |
|:--|:--|:--|
| `PCFG_VERSION_REQUIRED` | error | Present layer lacks `contract_version`; no effective config. |
| `PCFG_VERSION_UNSUPPORTED` | error | Version is malformed or outside the reader's supported major/minor; no fallback. |
| `PCFG_SCHEMA_INVALID` | error | Wrong JSON type, empty required map, `null`, or deletion marker. |
| `PCFG_UNKNOWN_FIELD` | error | Unknown key inside the fleet provider envelope or any layer/selection record. |
| `PCFG_UNKNOWN_PROVIDER` | error | Selection key is not a catalog Provider ID, even when its value is `false`. |
| `PCFG_UNKNOWN_CAPABILITY` | error | Capability key is absent from the catalog, even when `false`. |
| `PCFG_UNKNOWN_NATIVE_EXTENSION` | error | Native Extension key is absent from the catalog, even when `false`. |
| `PCFG_EXTENSION_PROVIDER_MISMATCH` | error | Extension namespace/manifest owner differs from the containing Provider. |
| `PCFG_DUPLICATE_FLEET_PROJECT` | error | More than one fleet record matches the canonical project ID. |
| `PCFG_LAYER_CONFLICT` | error | More than one candidate exists at any rank or its source identity is ambiguous. |
| `PCFG_CAPABILITY_UNSUPPORTED` | error | Explicit `true` requests a Capability whose Support Level is `unsupported`. |
| `PCFG_LEGACY_DEFAULT_APPLIED` | info | No explicit layer exists; Claude-compatible in-memory fallback was used. |

Unknown field/identity/version diagnostics are never downgraded to warnings. One Provider's
valid selection cannot mask an error in another Provider, and no diagnostic authorizes a
write or repair.

## Versioning

Each explicit layer MUST declare `contract_version`. A v1.0 reader accepts `1.0.x` because a
patch cannot change schema or semantics. It rejects a higher minor until that reader explicitly
declares support and rejects every unknown major. It MUST NOT guess from keys, silently strip
unknowns, or retry as legacy after a version error.

- **major:** changes carrier identity/precedence, Provider/Capability/Native Extension
  selection meaning, merge behavior, compatibility default, provenance ownership, error
  fail-closed behavior, or removes/renames a frozen field/code;
- **minor:** adds an optional understood input field, selection kind, or diagnostic without
  changing existing effective results;
- **patch:** editorial clarification or additional golden case without changing valid input,
  effective output, severity, code, precedence, or provenance.

Unknown structural fields are errors at every nesting level; `_comment`, `$schema`, and other
package-level allowances outside the provider subtree do not open extension points inside it.
Unknown Provider, Capability, or Native Extension IDs are errors regardless of boolean value.
Catalog evolution remains governed by the capability contract; the resolver records the
observed catalog version and fails on its unknown major before config resolution.

## Golden examples

All examples use a synthetic catalog fixture with Providers `claude-code` and `codex`, common
Capabilities `instructions.project`, `skills.repository`, and `hooks.lifecycle`, Native
Extensions `claude-code.fixture-native` and `codex.fixture-native`, and
`hooks.lifecycle = unsupported` for `codex`. Fixture IDs demonstrate schema only and make no
external provider claim.

### Positive: legacy no-write

Given no `providers` key in any carrier, the exact effective selection is:

```json
{
  "claude-code": {"enabled": true, "capabilities": {}, "native_extensions": {}},
  "codex": {"enabled": false, "capabilities": {}, "native_extensions": {}}
}
```

The two `enabled` provenance records both name `legacy:claude-code-compat`, carrier `legacy`,
source path `/`, and `explicit = false`. The sole diagnostic is info code
`PCFG_LEGACY_DEFAULT_APPLIED`, path `/`, source `legacy:claude-code-compat`. The
before/after bytes of `.swissknife.json` and `config.json` are identical.

### Positive: all compound fields resolve by identity

Fleet defaults (`config.json#/providers/defaults`):

```json
{"contract_version":"1.0.0","selection":{"claude-code":{"enabled":true,"capabilities":{"instructions.project":true},"native_extensions":{"claude-code.fixture-native":true}},"codex":{"enabled":false,"capabilities":{"skills.repository":false},"native_extensions":{"codex.fixture-native":false}}}}
```

Fleet project `demo` (`config.json#/projects/3/providers`):

```json
{"contract_version":"1.0.0","selection":{"codex":{"enabled":true,"capabilities":{"skills.repository":true},"native_extensions":{"codex.fixture-native":true}}}}
```

Project (`.swissknife.json#/providers`):

```json
{"contract_version":"1.0.0","selection":{"claude-code":{"enabled":false,"capabilities":{"instructions.project":false},"native_extensions":{"claude-code.fixture-native":false}},"codex":{"capabilities":{"skills.repository":false},"native_extensions":{"codex.fixture-native":false}}}}
```

Operation `deploy-check`:

```json
{"contract_version":"1.0.0","selection":{"codex":{"capabilities":{"skills.repository":true},"native_extensions":{"codex.fixture-native":true}}}}
```

The exact effective selection is:

```json
{
  "claude-code": {
    "enabled": false,
    "capabilities": {"instructions.project": false},
    "native_extensions": {"claude-code.fixture-native": false}
  },
  "codex": {
    "enabled": true,
    "capabilities": {"skills.repository": true},
    "native_extensions": {"codex.fixture-native": true}
  }
}
```

Exact winning provenance is:

| Effective path | Winner source | Source path |
|:--|:--|:--|
| `/selection/claude-code/enabled` | `project:demo` | `/providers/selection/claude-code/enabled` |
| `/selection/claude-code/capabilities/instructions.project` | `project:demo` | `/providers/selection/claude-code/capabilities/instructions.project` |
| `/selection/claude-code/native_extensions/claude-code.fixture-native` | `project:demo` | `/providers/selection/claude-code/native_extensions/claude-code.fixture-native` |
| `/selection/codex/enabled` | `fleet-project:demo` | `/projects/3/providers/selection/codex/enabled` |
| `/selection/codex/capabilities/skills.repository` | `operation:deploy-check` | `/selection/codex/capabilities/skills.repository` |
| `/selection/codex/native_extensions/codex.fixture-native` | `operation:deploy-check` | `/selection/codex/native_extensions/codex.fixture-native` |

This single case proves map merge by Provider ID, Capability ID, and Native Extension ID;
scalar replacement; preservation of unrelated siblings; and project ownership over fleet.

### Negative: stable diagnostic tuples

Every row is an error, returns `effective = null`, and performs no write.

| Invalid input/condition | Code | Path | Source |
|:--|:--|:--|:--|
| Project uses `selection.chatgpt` | `PCFG_UNKNOWN_PROVIDER` | `/providers/selection/chatgpt` | `project:demo` / `.swissknife.json#/providers` |
| Project uses capability `skills.unknown` | `PCFG_UNKNOWN_CAPABILITY` | `/providers/selection/codex/capabilities/skills.unknown` | `project:demo` / `.swissknife.json#/providers` |
| Project uses extension `codex.unknown` | `PCFG_UNKNOWN_NATIVE_EXTENSION` | `/providers/selection/codex/native_extensions/codex.unknown` | `project:demo` / `.swissknife.json#/providers` |
| `claude-code` contains `codex.fixture-native` | `PCFG_EXTENSION_PROVIDER_MISMATCH` | `/providers/selection/claude-code/native_extensions/codex.fixture-native` | `project:demo` / `.swissknife.json#/providers` |
| Provider record contains `options` | `PCFG_UNKNOWN_FIELD` | `/providers/selection/codex/options` | `project:demo` / `.swissknife.json#/providers` |
| Codex explicitly enables unsupported `hooks.lifecycle` | `PCFG_CAPABILITY_UNSUPPORTED` | `/providers/selection/codex/capabilities/hooks.lifecycle` | `project:demo` / `.swissknife.json#/providers` |
| Layer declares `contract_version: "2.0.0"` | `PCFG_VERSION_UNSUPPORTED` | `/providers/contract_version` | `project:demo` / `.swissknife.json#/providers` |
| Two fleet records have ID `demo` | `PCFG_DUPLICATE_FLEET_PROJECT` | `/projects` | `fleet-project:demo` / `config.json#/projects` |
| Two operation layers claim `deploy-check` | `PCFG_LAYER_CONFLICT` | `/` | `operation:deploy-check` / `operation#/` |

### Conflict: no implicit winner

If fleet defaults set `codex.enabled = true` and project config sets it to `false`, the exact
result is `false` with source `project:demo`; this is ordinary cross-rank replacement. If two
matched fleet records set conflicting values, resolution emits
`PCFG_DUPLICATE_FLEET_PROJECT` at path `/projects`, source `fleet-project:demo`, and returns no
effective config. If two operation candidates conflict, resolution emits
`PCFG_LAYER_CONFLICT` at path `/`, source `operation:<operation-id>`, and returns no effective
config. File/array order never breaks either tie.

## Validation

A conforming implementation and its golden fixture suite MUST prove:

1. all four explicit carriers parse into the same layer schema and remain no-write in
   parse/resolve/check/doctor;
2. precedence is exactly the five ranks above and each compound map follows the stated
   per-ID rule without a generic object merge;
3. every effective leaf has one winning provenance record and changing one key does not
   steal sibling provenance;
4. missing, explicit `false`, unsupported, unknown, and same-rank conflict remain distinct;
5. legacy projects resolve Claude Code-only without bytes changing or Codex enabling;
6. each negative golden returns the exact stable code/path/source tuple and no partial
   effective config;
7. both Provider rows are validated independently and one valid row cannot mask another
   row's error;
8. carrier/schema/catalog unknown majors and unknown structural fields fail before write.

Contract review uses the P1.1 section inventory, exact precedence scan, forbidden-placeholder
scan, JSON fence parsing, stable diagnostic tuple checks, `git diff --check`, and target
plan-lint. Package runtime/schema implementation and live carrier writes remain P1.2+ work.

## Approved Owner decision set (D70)

The Owner decision is substantive and atomic. Approval accepts all of:

- **F1 — carriers/schema:** the four explicit carriers, one uniform partial layer schema,
  stable IDs only, boolean provider/capability/Native Extension selection, and no option bag;
- **F2 — precedence/merge:** `operation > project > fleet project > fleet defaults > legacy`,
  per-ID map merge, highest defined scalar, explicit false wins, null forbidden, same-rank
  ambiguity fails;
- **F3 — compatibility:** synthetic Claude Code-only base, Codex/new Providers disabled,
  missing distinct from explicit disable, no implicit migration or write;
- **F4 — provenance/diagnostics:** leaf winner provenance, non-secret stable sources,
  mandatory severity/code/path/source, closed v1 codes, no partial effective result on error;
- **F5 — version/unknowns:** required per-layer version, supported patch only, unknown
  minor/major/field/identity fails closed, catalog version captured separately;
- **F6 — authority/examples:** the positive, negative, and conflict goldens are normative;
  this contract does not authorize implementation, provider output, FOREMAN, fleet, or live
  carrier mutation.

Exact approval reply:

```text
APPROVE P1.1 PROVIDER-CONFIG F1-F6 AS WRITTEN
```

Any change to F1-F6 is a requested revision, not partial approval. Only after the explicit
reply may lifecycle bookkeeping assign an Owner decision number. D70 records that exact
reply and freezes these F1-F6 bytes as v1.0.0; it opens only P1.2 and does not expand the
authority boundary stated in F6.
