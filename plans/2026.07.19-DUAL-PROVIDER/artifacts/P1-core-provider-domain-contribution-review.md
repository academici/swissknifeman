# P1.2 shared-core provider-domain contribution review

**Status:** proposed — explicit Approval Owner D# required before `core/**` edit
**Initiator:** `2026.07.19-DUAL-PROVIDER` P1.2
**Package:** monorepo shared package `core`
**Session:** gpt-5.6-terra/high
**Evidence:** frozen D53/D55/D70 contracts and P1.2 Required Reads; no external claim

## Go / no-go

**Verdict: GO, gated.** P1.2 may add the exact minimal public domain below only after
the Approval Owner accepts the atomic decision set in this document. The proposal is
not an implementation authorization and does not authorize P1.3+, provider output,
live carrier, FOREMAN, or fleet mutation.

### Rule of Three

The same immutable provider vocabulary is already a frozen dependency of at least four
independent named consumers; none can own it without reversing dependency direction.

| Consumer | Immediate use | Why it cannot be consumer-local |
|:--|:--|:--|
| P1.3 `skiller` + `maind` config adapters | resolve `ProviderId`, selections, provenance, diagnostics | Two carrier owners must produce identical IDs, closed severities/codes, and data envelopes. |
| P3 `skiller/publication` | declare adapter provider and required capability levels | A publication-only copy would disagree with P4/P5 capability gates. |
| P4 `task/command-contract` | declare provider projection requirements | Task cannot import `skiller` just to name a provider or capability. |
| P5 `harness/rendering` | preserve separate trust/approval/sandbox diagnostics while checking requirements | Harness must not inherit `skiller` config or renderer ownership. |
| P6 `maind/deployment` and `analyst/events` | consume provider identity/provenance without renderer ownership | Deployment and analytics cannot depend on a consumer package as their shared vocabulary source. |

These are plan-declared, frozen-contract consumers, not a claim that P1.2 will
implement their packages now. `core` is the only dependency direction permitted by
D14: consumers depend on the domain; `core` imports no consumer.

## Alternatives considered

1. **Keep local types in each package. Rejected.** It fails the named-consumer proof:
   P1.3 requires identical `skiller`/`maind` diagnostics and P3–P6 require the same
   IDs and support levels. Synchronizing strings by convention recreates a divergent
   public contract.
2. **Put an abstract registry/factory in `core`. Rejected.** A registry needs discovery,
   lifecycle, rendering, or I/O ownership; those belong to P2 and package adapters.
   It would add a service locator before any registry consumer is approved.
3. **Use untyped `dict[str, object]` envelopes across packages. Rejected.** It permits
   unknown normative fields and loses frozen validation, ordering, and SemVer surface.
4. **Create only constants, defer all immutable values. Rejected.** P1.3 must carry
   typed selection/provenance/diagnostic data across package boundaries; constants alone
   leave every consumer to invent its own data shape.

## Dependency direction and boundary

`core.provider` is stdlib-only and side-effect free. It imports neither `packages.*`
nor filesystem, environment, cwd, subprocess, printing, or provider-native libraries.
It does not discover adapters, parse carriers, merge config, render artifacts, write
locks, or branch on concrete provider behavior. P1.3 owns pure resolution; P2 owns
registry/artifact mechanics; P3–P6 own package-specific adapters and presentation.

```text
P1.3 skiller + maind ─┐
P3 skiller publication ├──> core.provider <── no imports from consumers
P4 task projections ───┤
P5 harness rendering ──┤
P6 maind / analyst ────┘
```

## Exact proposed immutable public API

The following is the complete proposed v1 surface of `core/provider.py`; no other
public symbol is authorized by this proposal. Every dataclass is `@dataclass(frozen=True)`;
all collection fields are tuples in documented deterministic order. Constructors reject
invalid/unknown-by-contract syntax but do not read a catalog or filesystem.

```python
class ProviderId(str, Enum):
    CLAUDE_CODE = "claude-code"
    CODEX = "codex"

class SupportLevel(str, Enum):
    NATIVE = "native"
    ADAPTED = "adapted"
    UNSUPPORTED = "unsupported"

class DiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

@dataclass(frozen=True, order=True)
class CapabilityId:
    value: str

@dataclass(frozen=True, order=True)
class NativeExtensionId:
    value: str

@dataclass(frozen=True, order=True)
class CapabilityRequirement:
    capability_id: CapabilityId
    accepted_levels: tuple[SupportLevel, ...]

@dataclass(frozen=True, order=True)
class ProviderDecision:
    identifier: CapabilityId | NativeExtensionId
    enabled: bool

@dataclass(frozen=True)
class ProviderSelection:
    provider_id: ProviderId
    enabled: bool | None
    capabilities: tuple[ProviderDecision, ...] = ()
    native_extensions: tuple[ProviderDecision, ...] = ()

@dataclass(frozen=True)
class EffectiveProvider:
    provider_id: ProviderId
    enabled: bool
    capabilities: tuple[ProviderDecision, ...] = ()
    native_extensions: tuple[ProviderDecision, ...] = ()

@dataclass(frozen=True, order=True)
class ConfigSource:
    kind: str
    id: str
    carrier: str
    path: str

@dataclass(frozen=True, order=True)
class ConfigProvenance:
    effective_path: str
    source: ConfigSource
    source_path: str
    explicit: bool

@dataclass(frozen=True, order=True)
class ProviderDiagnostic:
    severity: DiagnosticSeverity
    code: str
    path: str
    source: ConfigSource
    message: str = ""
    context: tuple[tuple[str, str], ...] = ()

class ProviderAdapter(Protocol):
    @property
    def adapter_id(self) -> str: ...
    @property
    def provider_id(self) -> ProviderId: ...
    @property
    def capability_requirements(self) -> tuple[CapabilityRequirement, ...]: ...
```

`ProviderDecision` is intentionally the one value used in either map; its runtime
validation requires `CapabilityId` only in `capabilities` and `NativeExtensionId` only
in `native_extensions`, with stable lexical ordering and no duplicate identifier. `ProviderId`
is closed to the frozen v1 pair. `CapabilityId` validates frozen lowercase dotted syntax;
`NativeExtensionId` validates provider-namespaced dotted syntax but leaves catalog membership
to P1.3's supplied manifest. `ConfigSource.kind` accepts exactly
`operation|project|fleet-project|fleet-defaults|legacy`; its other fields must be non-empty,
non-secret stable identifiers/pointers. `ProviderDiagnostic.code` remains a string because
P1.3 owns the frozen PCFG code set; its ordering is deterministic by `(severity, source,
path, code)`. `context` is immutable non-normative detail and does not replace the mandatory
severity/code/path/source envelope.

`core.__all__` will re-export exactly the 13 names above. `ProviderAdapter` is metadata-only:
rendering signatures remain package-owned because a common render method would invent a
registry/output contract before P2.

## Contract traceability

| Proposed symbol | Frozen anchor | Purpose |
|:--|:--|:--|
| `ProviderId` | capability contract: Vocabulary, Manifest envelope; config contract: ProviderConfigLayer | exact stable v1 pair, no aliases |
| `CapabilityId`, `SupportLevel`, `CapabilityRequirement` | capability contract: Capability record, Support Level invariants, Derived consumers | capability requirement before render |
| `NativeExtensionId` | capability contract: Native Extensions; config contract: ProviderSelection | provider namespace without false parity |
| `ProviderSelection`, `EffectiveProvider`, `ProviderDecision` | config contract: ProviderConfigLayer, EffectiveProviderConfig, Precedence and merge | pure selection values; no carrier I/O |
| `ConfigSource`, `ConfigProvenance` | config contract: Inputs and carriers, Provenance | leaf provenance with non-secret stable descriptors |
| `DiagnosticSeverity`, `ProviderDiagnostic` | config contract: Diagnostics | data envelope; packages localize presentation |
| `ProviderAdapter` | capability contract: Derived consumers; artifact contract: Artifact identity and provenance | metadata seam for P2 registry and P3–P6 adapters |

## SemVer consequence

This is an additive public API in `core`: **minor** version consequence for the next
published `core` contract, preserving all existing exports and behavior. No existing public
method/class/signature is removed, narrowed, renamed, or given a weaker output. Any later
rename/removal, changed enum string, changed validation meaning, reordered serialization, or
Protocol member made mandatory is a **major** change with ADR, CHANGELOG `Breaking:` entry,
and migration guide. A defect fix that preserves these semantics is patch-level.

## Atomic Owner decision set

Approval must accept every statement below together; a partial reply is a revision request.

- **G1 — Rule of Three:** P1.3, P3, P4, P5, and P6 are the named independent consumers;
  `core` is the only allowed dependency direction.
- **G2 — Boundary:** one flat, stdlib-only, side-effect-free `core.provider`; no I/O,
  registry, discovery, rendering, carrier parsing, provider-specific imports, or global state.
- **G3 — API:** authorize exactly the 13 exported symbols and fields shown above, with
  frozen dataclasses, tuple collections, closed enum strings, and stated validation limits.
- **G4 — Protocol seam:** `ProviderAdapter` is metadata-only; P2/P3–P6 retain registry and
  rendering ownership, and no extra Protocol method is implied.
- **G5 — Compatibility:** additive minor public API; any incompatible later change follows
  major-version ADR/CHANGELOG/migration rules.
- **G6 — Scope:** this approval authorizes only P1.2 `core/provider.py`, exports, and focused
  tests; it does not authorize P1.3+, package runtime, provider outputs, live carriers,
  FOREMAN, fleet, or contract edits.

Exact approval reply:

```text
APPROVE P1.2 CORE-PROVIDER G1-G6 AS WRITTEN
```

Only after that reply may lifecycle bookkeeping assign an Owner D# and P1.2 edit `core/**`.

## Adversarial review before approval

- **Speculative framework risk:** rejected — no registry, factory, discovery, renderer, or
  lifecycle method is proposed.
- **Consumer leakage:** blocked — static forbidden-import validation and no path/output field
  keep all carrier/render ownership outside `core`.
- **Frozen-contract drift:** blocked — every symbol has an exact frozen-contract anchor;
  P1.3 retains catalog membership and PCFG code semantics.
- **False immutability:** blocked — frozen dataclasses use tuples rather than mutable maps/lists;
  tests must verify mutation failure, equality, ordering, and serialization projections.
- **Premature approval attribution:** blocked — no D# is assigned here; only the owner may
  accept G1–G6 using the exact reply.
