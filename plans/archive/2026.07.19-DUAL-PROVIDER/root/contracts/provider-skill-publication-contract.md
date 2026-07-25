# Provider skill publication contract

**Version:** v1.0.0

**Status:** frozen

**Approval Owner:** Dmitry Vostrikov

**Approval:** D77, 2026-07-20

**Basis:** P3.1 · D20–D23 · frozen provider capability, artifact, config and migration-gates v1.0.0 contracts

## Purpose

This contract defines one provider-neutral semantic catalog for skiller skill
publication. Claude Code and Codex projections are independent render targets of
that catalog; neither provider manifest is an input to the other. It defines only
skill/publication identity and delivery boundaries. Task invocation syntax, trust,
permissions, MCP, hooks, live installs, FOREMAN and fleet are outside this contract.

The normative words MUST, MUST NOT, SHOULD and MAY are literal.

## Identity

- A **semantic skill ID** is the canonical registry identity
  `<bucket>/<frontmatter-name>`. It MUST identify the canonical `SKILL.md` content,
  not a provider path, marketplace key or cache location.
- A **plugin ID** is a stable marketplace/plugin name. Existing Claude bucket names,
  `core`, `generate-skill` and `skm` retain their names; they MUST NOT be renamed by a
  provider projection.
- A **publication-unit ID** is one of `bucket:<bucket>`, `core`,
  `generate-skill`, or `skm`. A unit has one ordered semantic member set and zero or
  more provider projections. Provider-specific path, manifest key and install state
  are attributes of a projection, never of the unit ID.
- A **provider projection** identifies `(provider_id, publication-unit ID, channel,
  target identity)`. `provider_id` MUST be a frozen capability-contract Provider ID;
  the initial set is `claude-code` and `codex`.
- An unknown, duplicate or path-derived semantic skill/plugin/publication-unit ID is
  invalid and MUST block render before a managed artifact is written.

## Publication units

The semantic catalog MUST contain exactly the following P3-owned unit classes:

| Unit | Semantic members | Canonical source | P3 boundary |
|:--|:--|:--|:--|
| `bucket:<bucket>` | ordered skills in one canonical bucket | `packages/skiller/skills/<bucket>/` | direct skill plugin |
| `core` | the ordered allowlist in `configs/core-policy.json` | canonical skill directories named by that policy | curated/discontiguous unit |
| `generate-skill` | its canonical authoring skill | `packages/skiller/generate-skill/` | standalone meta unit |
| `skm` | management intent over the existing skiller CLI | `packages/skiller/skm/` and declared skill adapter material | provider-native management unit |

The catalog MUST be built from canonical registry/policy inputs in deterministic
lexicographic unit/member order, except where `core-policy.json` deliberately supplies
the member order. It MUST NOT infer a set from a rendered Claude or Codex manifest.
Sibling package plugins remain owned by their package manifests; P3 may preserve their
existing Claude marketplace entries but MUST NOT recast them as skiller semantic skill
units without a later contract change.

`SKILL.ru.md`, `evals/`, `upstream.json`, references and service files are source or
maintenance material, not consumer bundle members, unless an explicit unit member rule
names a runtime-required file. A projection MUST record every included file through
artifact provenance; implicit directory copying is forbidden.

## Modes

| Mode | Semantic input | Claude Code projection | Codex projection | Required result |
|:--|:--|:--|:--|:--|
| direct plugin | one bucket unit | generated plugin/marketplace entry referring to canonical bucket | generated native plugin/marketplace entry referring to the declared direct unit root | same semantic member IDs |
| curated bundle | `core` or other discontiguous unit | generated curated marketplace projection | deterministic self-contained generated plugin bundle | cache-contained readable members |
| project self-host | canonical source available in the same repository | existing Claude project surface | thin `.agents/skills` adapter | adapter points only to same-repository canonical source |
| vendor consumer | selected semantic unit set | managed rendered skill copy | managed rendered skill copy | lock/provenance-backed copy, never a new canonical source |
| explicit native install | already-rendered Codex projection | no new Claude operation | native marketplace/plugin install action | separate explicit action only |

Mode selection MUST be explicit in the caller-built publication plan. A direct reference
outside an installed plugin root is invalid for a cache-loaded projection and MUST produce
a diagnostic instead of a thin external link. A vendor copy and a curated bundle are
derived artifacts governed by the frozen artifact contract; local edits are drift, not
an invitation to adopt a second source.

## Ownership

- Canonical skill content remains under `packages/skiller/skills/`; task command canon
  remains under `packages/task/commands/`. `.agents/skills` is a thin adapter surface,
  not a canonical tree.
- The semantic catalog is package-owned by skiller. A provider renderer receives an
  immutable catalog and explicit roots; it MUST NOT perform filesystem/import discovery,
  global registration, or provider-manifest-to-provider-manifest conversion.
- Generated manifests, curated bundles, vendor copies and their locks are manager-owned
  only when exact artifact provenance matches the expected projection. Unowned,
  malformed, stale-major or ambiguous targets MUST fail closed under the artifact
  contract's observation/action rules.
- A self-host thin adapter is allowed only where its canonical source remains inside the
  same repository at use time. Otherwise the consumer receives a self-contained,
  deterministic managed copy with source/content hashes and a lock.

## Versioning

Publication-unit IDs and semantic skill IDs are compatibility identities. Removing,
renaming or changing their observable membership is a catalog-major change. Adding a new
unit or additive provider projection is catalog-minor; evidence-only clarification is
catalog-patch.

For P3-owned units, the single plugin-version source is
`packages/skiller/package.json::version`. Claude and Codex manifests for the same P3-owned
unit MUST render that value identically. A renderer MUST NOT derive a version from a
directory timestamp, cache path, generated byte hash or provider CLI version. A sibling
package retains its package-owned version source.

The contract version is independent of the publication catalog version. Unknown contract
major, unknown catalog major or a projection whose declared version cannot be traced to its
defined source MUST block render/check/apply with a diagnostic.

## Provider projections

Each provider projection MUST be rendered independently from the same semantic catalog and
MUST record its publication-unit ID, provider ID, channel, target identity, selected member
IDs, version source/value, canonical source identities, adapter identity/version, capability
requirements, source hash and rendered hash.

Claude Code projections preserve the existing marketplace and plugin identity/bytes unless a
separate approved compatibility change says otherwise. Codex projections use the native plugin
manifest and repository marketplace shapes defined by the capability evidence. A Codex
marketplace local source path MUST be `./`-prefixed, relative to the marketplace root and
contained by it. A renderer MUST validate its required capability IDs and accepted support
levels before it creates a projection.

No projection may enable a provider merely because another provider is selected. The P1
resolver is the only source of effective provider selection and its provenance.

## Install boundary

Render, check, doctor, dry-run and ordinary update are project-artifact operations. They MUST
NOT execute a native installer, mutate a user-global Codex location or infer consent from
project trust, provider selection or a legacy configuration.

A user-global Codex plugin/marketplace installation is a distinct explicit operation over an
already validated native projection. It MUST report provider, channel, target, source/rendered
hashes and outcome separately from the project artifact transaction. The exact public command
surface is deliberately deferred to P3.4; this contract authorizes no new public CLI command.
Failure or absence of the native installer is a provider-qualified diagnostic and MUST NOT make
another provider's project result appear wholly successful.

## Compatibility

Legacy configuration with no provider layer resolves through the frozen P1 compatibility rule:
`claude-code` is selected and `codex` is not implicitly enabled. Explicit disable remains
different from missing configuration.

Existing Claude plugin names, marketplace identities, `enabledPlugins` semantics and generated
bytes are compatibility gates. Codex support is additive: no legacy target is rewritten merely
because the catalog gains a Codex projection. Unsupported capability, missing native install
prerequisite, unmanaged target, corrupt lock or projection/version mismatch fails closed and
does not adopt or overwrite a path.

## Diagnostics

The catalog/renderer/operation boundary MUST emit one provider-qualified, actionable code for
at least these conditions:

| Code | Condition | Required outcome |
|:--|:--|:--|
| `SPUB_ID_INVALID` | invalid, duplicate or path-derived semantic identity | refuse before render |
| `SPUB_CATALOG_MISMATCH` | projection membership/version differs from catalog | refuse before write |
| `SPUB_CAPABILITY_UNSUPPORTED` | a required capability is absent or not at an accepted level | refuse/no write |
| `SPUB_PATH_UNCONTAINED` | marketplace/plugin/cache path escapes its declared root | refuse/no write |
| `SPUB_BUNDLE_INCOMPLETE` | cache-contained projection lacks a declared member | refuse/no write |
| `SPUB_OWNERSHIP_CONFLICT` | target provenance/lock is absent, corrupt or belongs to another artifact | artifact-contract refusal |
| `SPUB_INSTALL_EXPLICIT_REQUIRED` | a non-explicit operation requests native global installation | no subprocess/no write |
| `SPUB_INSTALL_UNAVAILABLE` | explicit native install cannot run or fails | provider-qualified blocked/mixed result and repair guidance |

Diagnostics MUST name the provider ID, publication-unit ID, channel and target identity where
available. `check`, `doctor` and dry-run MUST use the immutable publication plan and make no
writes.

## Golden examples

### G1 — direct bucket, legacy Claude-only

| Semantic input | Claude output | Codex output / diagnostic |
|:--|:--|:--|
| effective selection is legacy `claude-code`; unit `bucket:general`; canonical members are the registry's ordered `general/*` skills | existing `general` marketplace/plugin identity and bytes are rendered from the catalog | no Codex projection is selected; no Codex file or install action is produced |

### G2 — curated core for both selected providers

| Semantic input | Claude output | Codex output / diagnostic |
|:--|:--|:--|
| both providers selected; unit `core`; members are the ordered `core-policy.json::skills` allowlist | curated `core` projection contains exactly those semantic IDs and its declared skiller package version | self-contained cache-contained `core` bundle contains exactly the same IDs and records lock/provenance hashes; an external thin path is `SPUB_PATH_UNCONTAINED` |

### G3 — self-host adapter versus vendor consumer

| Semantic input | Claude output | Codex output / diagnostic |
|:--|:--|:--|
| a project is self-hosting with canonical source in the same repository | existing selected Claude projection is unchanged | `.agents/skills` may be a thin adapter to that same-repository canonical source; a vendor target without the source instead receives a locked rendered copy |

### G4 — explicit-install boundary

| Semantic input | Claude output | Codex output / diagnostic |
|:--|:--|:--|
| valid rendered Codex `skm` projection, but operation is `doctor` or ordinary `update` | no install operation is implied | `SPUB_INSTALL_EXPLICIT_REQUIRED`; native installer subprocess count is zero |

### G5 — invalid cache/ownership state

| Semantic input | Claude output | Codex output / diagnostic |
|:--|:--|:--|
| a Codex curated bundle target has a lock for a different artifact ID or misses a declared member | unaffected projection remains independently classified | `SPUB_OWNERSHIP_CONFLICT` or `SPUB_BUNDLE_INCOMPLETE`; refuse without write |

## Approval

The Approval Owner accepted the complete S1–S6 set as D77 on 2026-07-20. This document is
frozen v1.0.0 and authorizes only the P3.1 contract close; downstream implementation remains
bounded by its own item scope and routing.

1. **S1 — one semantic catalog.** Stable semantic skill/plugin/publication-unit IDs and the
   P3-owned unit classes in this document are the only publication identity source.
2. **S2 — independent native projections.** Claude and Codex manifests render independently
   from that catalog; neither manifest is a canonical input or conversion source for the other.
3. **S3 — ownership and bundles.** Canonical sources remain in skiller/task; thin adapters are
   same-repository only, while cache/vendor outputs are deterministic self-contained or locked
   derived artifacts.
4. **S4 — versions and compatibility.** P3-owned plugin version derives only from
   `packages/skiller/package.json::version`; legacy provider absence remains Claude-only and
   existing Claude identities/bytes remain a compatibility gate.
5. **S5 — install boundary.** Native user-global Codex installation is explicit and separate;
   render/check/doctor/dry-run/default update cannot invoke it or create a public command by
   implication.
6. **S6 — fail-closed diagnostics.** Identity, containment, capability, cache completeness,
   ownership and explicit-install failures are provider-qualified no-write diagnostics.

**Recorded owner decision:** `APPROVE P3.1 SKILL-PUBLICATION S1-S6 AS WRITTEN` → D77.
