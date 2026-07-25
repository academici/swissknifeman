# P7.1 capability manifest and shared-core contribution review

**Status:** approved and frozen by Owner D99; P7.1 production switch authorized

**Candidate:** `configs/provider-capabilities.json`

**Contract / catalog:** `1.0.0` / `1.0.0`

**Canonical SHA-256:** `4c479c697c708cfea8d36589c435338094d894bcf428687709987975b13b6ce1`

**Canonicalization:** UTF-8 `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`; the carrier is those bytes plus one terminal LF.
**Carrier SHA-256:** `32975d675cf252bba87b06aaee53bfe37e63a9a97dc74cb7a12a8a2b0c0394eb` (includes the terminal LF and is intentionally distinct from the approved canonical digest).
**Approved set:** 2 providers, 35 common capabilities, 0 Native Extensions.

At the pre-approval review checkpoint no `core`, package source/test, docs generator,
README, operator guide, provider output, live target, FOREMAN or fleet consumer had been
changed. D99 subsequently authorized the bounded P7.1 production switch only.

## Exact-set derivation

The inventory is independent of rendered provider output:

| Owning terminal source | Exact contribution | Reason |
|:--|:--|:--|
| P3 skill-publication contract/catalog/conformance | `skills.repository` | One common repository/plugin loading promise used by both publication adapters. |
| P4 frozen command contract and `packages/task/configs/command-routing.json` | 7 `command.*` IDs; the eighth command requirement is the already-counted `skills.repository` | Exact v1 requirement vocabulary and provider support bindings. |
| P5 frozen harness contract plus common profile catalog | 23 frozen Surface IDs, reused as common Capability IDs | These are the cross-provider observable intents whose support/binding/diagnostic must move from the package-local matrix into the D3 manifest. The package catalog continues to own intent, grouping and requirements. |
| P5 frozen instruction contract/catalog/conformance | `instructions.project` | The capability-contract golden and P5 lock already use this common requirement. |
| P6 frozen analytics contract, accepted review and terminal readers/store/migration | `analytics.normalized-events`, `analytics.run-report`, `analytics.legacy-migration` | Minimum separable promises actually implemented and consumed: normalization/store, neutral projection and the Claude-only bounded legacy migration. |

The three analytics IDs materialize existing terminal P6 semantics as initial catalog
content; they do not add a field or change the frozen analytics/capability contracts.

`native_extensions=[]` is deliberate. The P5 instruction catalog's 18
`provider-extension` section IDs are instruction records, not capability-contract Native
Extensions: their identity is scope-namespaced (for example
`root.claude-code.native-surfaces`) rather than beginning with `<provider-id>.`, and they
are not config-selectable parity claims. Transforming them into new IDs would invent a
second identity set. No other terminal catalog declares a conforming Native Extension ID.

## Exact support matrix

| Capability | Claude Code | Codex |
|:--|:--|:--|
| `agent-packs.lifecycle` | adapted | unsupported |
| `agents.catalog` | adapted | adapted |
| `analytics.legacy-migration` | adapted | unsupported |
| `analytics.normalized-events` | adapted | adapted |
| `analytics.run-report` | adapted | adapted |
| `command.external-research` | adapted | adapted |
| `command.filesystem-read` | native | native |
| `command.filesystem-write` | native | native |
| `command.git-read` | native | native |
| `command.git-write` | native | native |
| `command.subagents` | native | native |
| `command.workflow-carrier` | native | adapted |
| `context.observer` | unsupported | native |
| `context.output-style` | native | unsupported |
| `context.plans-directory` | native | unsupported |
| `doctor.environment` | adapted | adapted |
| `doctor.provider` | adapted | adapted |
| `instructions.project` | native | native |
| `lifecycle.auto-approval` | adapted | native |
| `lifecycle.changelog-gate` | adapted | unsupported |
| `lifecycle.command-log` | adapted | unsupported |
| `lifecycle.daemon-safety` | unsupported | unsupported |
| `lifecycle.git-guardrails` | unsupported | unsupported |
| `lifecycle.memory` | adapted | unsupported |
| `lifecycle.notification` | adapted | unsupported |
| `lifecycle.pack-guard` | adapted | unsupported |
| `lifecycle.review-gate` | adapted | unsupported |
| `lifecycle.router` | adapted | unsupported |
| `lifecycle.run-report` | adapted | unsupported |
| `mcp.catalog` | adapted | adapted |
| `security.safe-dirs` | adapted | unsupported |
| `settings.audit` | adapted | unsupported |
| `settings.permissions` | adapted | adapted |
| `skills.repository` | native | native |
| `workflows.status` | adapted | unsupported |

Totals over 70 support records are 19 `native`, 31 `adapted` and 20 `unsupported`:
Claude Code is 10/22/3; Codex is 9/9/17. Package-rendered or package-operated harness
promises are conservatively `adapted`; only terminally evidenced provider-native
configuration/context promises are `native`. An unsupported P5 row remains visible and
fail-closed rather than being promoted from the presence of source code or a rendered file.

## Current consumers and Rule of Three

| Consumer | Current use | Why a local solution is invalid |
|:--|:--|:--|
| skiller | `skills.repository` gates the Claude and Codex publication adapters; `resolve_distribution_providers` currently builds a local two-row catalog. | A skiller-owned support map cannot validate task, harness or maind and would become a second D3 source. |
| task | Eleven semantic commands consume the exact P4 capability vocabulary; command renderers currently accept a caller-owned free-form support mapping. | The mapping needs the same catalog version, evidence and support semantics as publication/deployment. |
| harness | The frozen 23-surface catalog, MCP/agent/instruction projections and provider audit currently compute/report provider support locally. | The package must retain semantic intent but cannot also own cross-provider support/binding/diagnostic after D3. |
| maind | Provider config/deploy/onboard/sync need catalog validation before provider artifact work; one current deploy path constructs an empty local catalog. | Deployment cannot infer support from outputs or select a package-specific fallback. |
| root docs/doctor | README matrix, operator guide and diagnostics must derive from the same validated records. | A docs-only aggregator would be self-confirming and could not gate pre-render work. |

**Rule-of-Three verdict: GO.** Four independent production package consumers plus the
root docs/diagnostic consumer need the same immutable support records now. None can solve
the requirement locally because D3/D55 require one manifest and because config/registry
gates precede package render. This is a current repeated seam, not speculative reuse.

## Existing extension-point survey

- `core.provider` already owns immutable `ProviderId`, `CapabilityId`,
  `NativeExtensionId`, `SupportLevel` and `CapabilityRequirement`; no new provider enum or
  base service is needed.
- `core.provider_config.ProviderConfigCatalog` is the frozen compact projection required
  by config resolution. The manifest should create it, not replace or expand its meaning.
- `core.provider_registry.AdapterCatalog.select(...)` already performs the fail-closed
  provider/capability/catalog-version gate when supplied a `ProviderConfigCatalog`.
- `core.provider_artifact.canonical_json_bytes` and `sha256_digest` already define the
  deterministic JSON/hash primitives; the manifest module should reuse them.
- skiller and maind already accept a `ProviderConfigCatalog` at lower boundaries; task
  already accepts an explicit support map; harness owns explicit catalogs. The missing
  seam is a validated projection, not discovery or registration.

No existing extension point holds the rich `intent/binding/limitations/evidence/diagnostic`
record. Putting those fields directly into `ProviderConfigCatalog` would couple frozen P1
selection semantics to presentation/evidence and needlessly widen every resolver fixture.

## Alternatives reviewed

| Alternative | Result | Verdict |
|:--|:--|:--|
| Package-local validators/support maps | Small local diffs, but at least four truths, unequal versions/evidence and no root exact-set. | Reject. |
| Root docs script parses package reports | Avoids core API, but report/output becomes support truth and production adapters remain ungated. | Reject. |
| Put the rich model in skiller, harness or maind | Makes sibling packages depend on a consumer and reverses package direction. | Reject. |
| Expand `ProviderConfigCatalog` with every rich manifest field | One type, but mixes D55 support evidence with D70 selection input and expands a stable API used by resolver tests. | Reject. |
| Global registry/import or cwd/home discovery | Convenient call sites, but output depends on import/environment order and can select linked-worktree, home or fleet state. | Reject. |
| Flat `core.provider_manifest` model + pure validation + explicit loader + compact P1 projection | One rich source, preserves existing catalog/registry contracts and explicit dependency flow. | Choose. |

## Proposed minimal additive core API

All new values are frozen dataclasses in one stdlib-only
`core/provider_manifest.py`. JSON objects stored as metadata are recursively frozen to
ordered tuples; callers receive detached mappings rather than mutable internal state.

```python
@dataclass(frozen=True, order=True)
class ManifestEvidence:
    source: str
    verified_at: str
    scope: str
    claim: str

@dataclass(frozen=True)
class ManifestSupport:
    provider_id: ProviderId
    level: SupportLevel
    binding: tuple[tuple[str, object], ...] | None
    adapter_id: str | None
    limitations: tuple[str, ...]
    evidence: tuple[ManifestEvidence, ...]
    diagnostic: str

@dataclass(frozen=True)
class ManifestCapability:
    capability_id: CapabilityId
    intent: str
    support: tuple[ManifestSupport, ...]

@dataclass(frozen=True)
class ManifestNativeExtension:
    extension_id: NativeExtensionId
    provider_id: ProviderId
    intent: str
    binding: tuple[tuple[str, object], ...]
    evidence: tuple[ManifestEvidence, ...]
    diagnostic: str

@dataclass(frozen=True)
class ProviderCapabilityManifest:
    contract_version: str
    catalog_version: str
    providers: tuple[ProviderId, ...]
    capabilities: tuple[ManifestCapability, ...]
    native_extensions: tuple[ManifestNativeExtension, ...]

class ProviderManifestError(ValueError):
    diagnostics: tuple[ProviderManifestDiagnostic, ...]

def parse_provider_manifest(
    value: bytes | Mapping[str, object], *, source_id: str = "memory"
) -> ProviderCapabilityManifest: ...

def load_provider_manifest(path: Path) -> ProviderCapabilityManifest: ...

def provider_config_catalog(
    manifest: ProviderCapabilityManifest,
) -> ProviderConfigCatalog: ...

def provider_support_projection(
    manifest: ProviderCapabilityManifest, provider_id: ProviderId,
) -> Mapping[str, SupportLevel]: ...

def provider_manifest_canonical_bytes(
    manifest: ProviderCapabilityManifest,
) -> bytes: ...

def provider_manifest_sha256(
    manifest: ProviderCapabilityManifest,
) -> str: ...
```

`ProviderManifestDiagnostic` is an immutable `(code, path, message)` record. Validation
aggregates deterministic path-sorted diagnostics and raises one `ProviderManifestError`;
no partial manifest or compact projection is returned. Stable code families are:
`MANIFEST_VERSION_UNSUPPORTED`, `MANIFEST_SCHEMA_INVALID`,
`MANIFEST_PROVIDER_INVALID`, `MANIFEST_CAPABILITY_INVALID`,
`MANIFEST_SUPPORT_MATRIX_INVALID`, `MANIFEST_SUPPORT_LEVEL_INVALID`,
`MANIFEST_SUPPORT_INVARIANT`, `MANIFEST_EVIDENCE_INVALID`,
`MANIFEST_EXTENSION_INVALID`, and `MANIFEST_SECURITY_AXES_COLLAPSED`.

The parser accepts only exact v1 envelope/record keys, decodes UTF-8 JSON with duplicate
object-key detection, validates SemVer/provider and capability identity, exact provider
matrix cardinality, all native/adapted/unsupported invariants, non-empty evidence and
diagnostics, extension namespace/owner, and the forbidden combined security/autonomy
value. Unknown contract major or unknown field fails closed. It sorts identity sets but
does not reinterpret their meaning.

`load_provider_manifest(path)` reads exactly the caller-supplied `Path`; it performs no
cwd/repository/home/fleet/worktree search and has no fallback. Package entry points compute
the repository-owned path explicitly and pass the rich manifest, its compact projection or
one provider support projection onward. `provider_config_catalog` reuses the existing
`CapabilitySupport`/`NativeExtension` types and preserves `catalog_version` byte-for-byte.
No global cache, registration hook, service locator or provider branch is introduced.

## Dependency direction and production switch shape

```text
configs/provider-capabilities.json
            |
            v
core.provider_manifest --pure--> core.provider_config.ProviderConfigCatalog
            |
            +--> skiller publication/config gate
            +--> task command support gate
            +--> harness profile/MCP/agent/instruction audit gate
            +--> maind deploy/onboard/sync gate
            +--> root docs write/check
```

`core` imports only its existing core siblings and stdlib. No package imports enter core;
no package imports another package to obtain support truth. Package catalogs continue to
own skill/command/surface/instruction/analytics intent and declare requirements, while the
manifest alone owns level/binding/limitations/evidence/diagnostic. The production change
must be atomic in P7.1: all listed entry points consume the validated projection, and local
hard-coded/free-form support constructors are removed rather than retained as fallback.

## Proposal / ADR / SemVer mapping

- Proposal carrier: D98 plus
  `research/22-p7-capability-manifest-remediation.md` and
  `findings/P7.1-capability-manifest-gap-2026-07-22.md` define the current consumers,
  missing seam, alternatives and authority boundary.
- ADR: accepted ADR-0001 already chooses one capability manifest, deterministic
  provider adapters and fail-closed pre-render gates. The proposed module implements that
  decision; it does not introduce a new architecture choice, so a second ADR is not needed.
- Capability **contract** remains `1.0.0`: no frozen key, level meaning or validation rule
  changes.
- Capability **catalog** starts at `1.0.0`: this is the first normative carrier. The 35
  records and empty extension set are the initial exact catalog, not a change from a prior
  published catalog.
- Shared `core` public surface is an additive **minor** change: new exported dataclasses and
  functions, with existing `ProviderConfigCatalog`, resolver and registry signatures kept
  backward compatible. Any later removal/signature tightening is major.

## Operational risks and rollback

| Risk | Gate / rollback |
|:--|:--|
| Wrong support level or stale evidence blocks valid work or overclaims parity. | Owner approves exact canonical hash and matrix; terminal package conformance must match independently. Revert the P7.1 item commit as one unit if the matrix is wrong. |
| Some consumer retains a local fallback. | Production grep/exact-set tests require all four package seams to load the same catalog version/hash; missing manifest must fail before write. |
| Rich model silently mutates or loses JSON meaning. | Frozen dataclasses, recursive metadata freeze, canonical round-trip/hash and duplicate-key negative tests. |
| Loader resolves the wrong checkout/home/fleet file. | Exact supplied path only; no search/fallback/cache. Rollback is removal of consumer switch plus restoration of prior local constructors from the item commit. |
| Docs become a second support canon. | `--write` and no-write `--check` consume the validated manifest; generated blocks carry contract/catalog/canonical SHA. |
| Initial analytics/native-extension classification is wrong. | D99 is atomic; revise candidate and hash before approval. After approval, any incompatible catalog change follows capability-catalog SemVer rather than a local exception. |

The candidate itself is non-live and reversible. No production consumer is switched until
the exact approval below is received and recorded.

## Atomic Owner D99 decision payload

D99 accepts all of the following, atomically:

1. canonical manifest SHA-256
   `4c479c697c708cfea8d36589c435338094d894bcf428687709987975b13b6ce1`,
   contract/catalog `1.0.0/1.0.0`, providers `claude-code,codex`;
2. the exact ordered 35-capability set and complete 70-row support matrix printed above,
   including three terminal-evidence-backed analytics IDs and 0 Native Extensions;
3. evidence freshness through P3/P4/P5 `2026-07-21` and P6 `2026-07-22`, with no claim
   inferred from live output;
4. the exact additive flat `core.provider_manifest` API, deterministic fail-closed
   validation/error shape, supplied-path-only loader and projection to the unchanged
   `ProviderConfigCatalog`;
5. catalog initial release `1.0.0`, unchanged frozen contract `1.0.0`, and additive shared
   `core` public API classified as minor;
6. authority only to finish P7.1 production gates/tests/docs/conformance. It does not
   authorize P7.2+, live install/apply/repair, bootstrap cleanup, FOREMAN, fleet, tag, push
   or any frozen-semantic change.

Exact approval reply:

```text
APPROVE P7.1 D99 CAPABILITY-MANIFEST SHA256:4c479c697c708cfea8d36589c435338094d894bcf428687709987975b13b6ce1 SETS-API-SEMVER AS WRITTEN
```

Any different hash, set, API, SemVer or authority boundary is a requested revision, not
partial approval. Production switching remains blocked until that exact reply is received.

## Received Owner decision

```text
APPROVE P7.1 D99 CAPABILITY-MANIFEST SHA256:4c479c697c708cfea8d36589c435338094d894bcf428687709987975b13b6ce1
SETS-API-SEMVER AS WRITTEN
```

D99 freezes the canonical bytes without the carrier LF, the exact sets/API/SemVer above,
and authorizes only P7.1 implementation, tests, generated docs and conformance evidence.
