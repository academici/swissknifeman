# Provider harness contract

**Version:** v1.0.0

**Status:** frozen

**Approval Owner:** Dmitry Vostrikov

**Approval:** D85, 2026-07-21 (delegated under D79)

**Basis:** D28–D32, D79/D82; frozen provider capability, configuration,
artifact, migration-gates, skill-publication and command-routing contracts v1.0.0

## Purpose

This contract defines the provider-neutral harness profile and surface catalog consumed by
the `harness` package and by later deployment/release phases. Common records describe stable
intent, security requirements, support state, target scope and managed ownership. Named
provider projections own native paths, keys, events, activation and serialization.

The contract does not authorize package implementation, live/user-global apply, provider
SDK use, resolved secret storage, FOREMAN/fleet mutation or implicit full access. Provider
selection and its provenance remain owned by the frozen configuration contract; artifact
identity, hashes, drift and repair remain owned by the frozen artifact contract.

Normative words `MUST`, `MUST NOT`, `SHOULD` and `MAY` are literal.

## Identity

The contract envelope contains exactly:

| Field | Contract |
|:--|:--|
| `contract_version` | Supported SemVer of this schema; this freeze is `1.0.0`. |
| `catalog_version` | SemVer of the profile/surface catalog. |
| `profiles` | Non-empty ordered set of unique Profile records. |
| `surfaces` | Non-empty ordered set of unique Surface records. |
| `projections` | Provider-keyed projection catalog, validated independently. |

A Profile ID and Surface ID are stable lowercase dotted identities. Each segment starts
with an ASCII lowercase letter and contains lowercase letters, digits or hyphens. IDs are
semantic identities: they MUST NOT be derived from a provider path, key, event, model,
display label or cache location. A removed ID is never reused with a new meaning.

The initial Provider set is exactly the frozen capability-contract set
`claude-code` and `codex`. Provider IDs, Capability IDs and Support Levels are consumed
without aliases or redefinition. Unknown, duplicate or path-derived identity fails before
render or write.

Every consumer receives an immutable, explicitly caller-built catalog. Filesystem discovery,
import-order registration, global mutable registries and output-to-output translation are
forbidden.

## Profiles

The common security profile set is closed in v1:

| Profile ID | Intent | Required security record | Full access |
|:--|:--|:--|:--|
| `observe` | Read/check/diagnose without activating project-owned executable surfaces or writing managed targets. | `trust=not-required`, `approval=provider-read-check`, `sandbox=read-only` | forbidden |
| `workspace-contained` | Operate autonomously only inside the explicit workspace and declared managed targets. | `trust=trusted-project`, `approval=provider-interactive-or-never`, `sandbox=workspace-contained` | forbidden |
| `trusted-full-access` | Perform one named trusted operation using the provider-native full-access boundary. | `trust=trusted-repository`, `approval=explicit-operation`, `sandbox=full-access` | explicit operation only |

Each Profile record contains exactly:

| Field | Contract |
|:--|:--|
| `id` | Stable Profile ID from the table. |
| `intent` | Observable provider-neutral promise. |
| `required_surfaces` | Ordered unique Surface IDs; every required failure makes the profile non-green. |
| `optional_surfaces` | Ordered unique Surface IDs that remain visible when unavailable. |
| `security` | Independent Trust, Approval and Sandbox requirements from `Security`. |
| `allowed_target_scopes` | Non-empty subset of `project`, `user`, `managed`. |

Current provider preset names and stack fragments are compatibility projection data, not
additional common Profile IDs. A caller MAY compose stack/surface selections with one common
security Profile, but composition cannot weaken its security record or enable an undeclared
Surface. Unknown profile or ambiguous composition is a no-write error.

## Surfaces

Each Surface record contains exactly:

| Field | Contract |
|:--|:--|
| `id` | Stable Surface ID. |
| `kind` | One of `settings`, `security`, `lifecycle`, `context`, `mcp`, `agents`, `agent-packs`, `workflows`, `doctor`. |
| `intent` | Observable provider-neutral promise. |
| `required_capabilities` | Ordered Capability requirements and accepted Support Levels. |
| `secret_refs` | Ordered secret-reference IDs; empty when no secret input is required. |
| `ownership` | Artifact ID/boundary policy reference, never a provider target path. |
| `required` | Whether failure makes the selected profile aggregate non-green. |

The initial exact common Surface set is:

| Surface ID | Kind | Intent |
|:--|:--|:--|
| `settings.permissions` | settings | Render named permission/settings presets without replacing user-owned values. |
| `settings.audit` | doctor | Read layered settings, compute effective values/provenance and report named policy conformance. |
| `security.safe-dirs` | security | Maintain and evaluate a machine-owned destructive-operation allowlist fail closed. |
| `lifecycle.auto-approval` | lifecycle | Apply the selected command/plan approval policy through a native lifecycle binding. |
| `lifecycle.memory` | lifecycle | Activate the selected memory lifecycle integration without changing its external state contract. |
| `lifecycle.notification` | lifecycle | Notify the operator on provider-native waiting/approval events. |
| `lifecycle.command-log` | lifecycle | Record provider-native command execution evidence. |
| `lifecycle.router` | lifecycle | Project semantic command/agent/skill routing into native lifecycle activation. |
| `lifecycle.run-report` | lifecycle | Capture a provider-qualified run report at a native lifecycle boundary. |
| `lifecycle.pack-guard` | lifecycle | Guard managed agent-pack assets before mutation. |
| `lifecycle.changelog-gate` | lifecycle | Gate declared release-sensitive operations against changelog policy. |
| `lifecycle.review-gate` | lifecycle | Gate declared review-sensitive lifecycle completion through machine-owned policy. |
| `lifecycle.daemon-safety` | lifecycle | Reject unsafe shared-daemon operations. |
| `lifecycle.git-guardrails` | lifecycle | Reject declared dangerous version-control operations. |
| `context.observer` | context | Activate the read-oriented observer context policy. |
| `context.output-style` | context | Select a provider-native output/context style. |
| `context.plans-directory` | context | Declare the project plan directory through a native configuration binding. |
| `mcp.catalog` | mcp | Render selected semantic MCP server descriptors with secret references only. |
| `agents.catalog` | agents | Render semantic agent roles/content/command requirements into native targets. |
| `agent-packs.lifecycle` | agent-packs | Render, check, upgrade, remove and diagnose locked packs without overwriting local edits. |
| `workflows.status` | workflows | Read and report provider-qualified workflow run status. |
| `doctor.environment` | doctor | Diagnose harness/package prerequisites without mutation. |
| `doctor.provider` | doctor | Compose named provider validators and catalog/activation diagnostics without pretending one provider's settings semantics are universal. |

The P5.1 review inventory maps every current package surface exactly once to this table.
Later implementation MAY split code internally, but changing the semantic set or intent is
catalog versioning, not an implementation detail.

## Security

Security is a product of three independent axes. A conforming Security record contains:

```json
{
  "trust_requirement": "not-required|trusted-project|trusted-repository",
  "approval_intent": "provider-read-check|provider-interactive-or-never|explicit-operation",
  "sandbox_intent": "read-only|workspace-contained|full-access",
  "explicit_operation_id": null,
  "target_identity": null,
  "inheritable": false
}
```

Rules:

1. Trust does not imply an Approval or Sandbox value.
2. Non-interactive approval does not expand the Sandbox Boundary.
3. A wider Sandbox Boundary does not establish trust or operation consent.
4. `trusted-full-access` is valid only when `explicit_operation_id` and exact
   `target_identity` are supplied by the current operation, trust is satisfied, and
   `inheritable=false`.
5. No default, project, matched-fleet, fleet-default or legacy layer may select or retain
   `trusted-full-access`; encountering it there is a hard no-write error.
6. Unknown, unavailable or ambiguous provider security mapping has no nearest-profile
   fallback.
7. A required Surface whose trust/capability/activation prerequisite fails blocks the
   profile before any artifact write. Optional failures remain structured diagnostics and
   MUST NOT be reported as parity.

`observe` MUST NOT activate executable project lifecycle surfaces. `workspace-contained`
MUST NOT write outside the explicit workspace/managed targets or expand network/external
path access from an approval choice. Full access remains forbidden in render/check/doctor,
ordinary update and fleet operations.

## Scopes and precedence

Target scope is one of:

| Scope | Contract |
|:--|:--|
| `project` | Repository-owned provider target after explicit project trust; project/user bytes outside managed boundaries remain user-owned. |
| `user` | User-global provider target; requires an explicit operation and is never implied by project selection. |
| `managed` | Administrator/machine-owned target; its native precedence and write authority are projection metadata. |

Provider enablement is resolved only by the frozen configuration precedence:
operation > project > fleet project > fleet defaults > legacy. The harness receives that
effective selection and provenance; it MUST NOT reread carriers, invent another provider
winner or persist fleet state into a project.

Harness profile selection is a distinct operation input. Missing profile uses only the
declared provider compatibility behavior; it does not mean full access. Explicit disable,
missing, unsupported, untrusted and unknown remain distinct.

Provider-native target precedence MUST be recorded per projection and validated by the
named provider adapter. There is no universal object merge. A projection declares each
field/boundary as `merge`, `replace-managed`, `remove-managed` or `read-only` and identifies
the provider-native winning layer. Cross-scope ambiguity fails before render. User-global
installation/activation and project artifact rendering are separate operations.

## Provider projections

Each projection record contains:

| Field | Contract |
|:--|:--|
| `provider_id` / `surface_id` | Stable identities from the frozen provider and Surface catalogs. |
| `support_level` | `native`, `adapted` or `unsupported` from the capability contract. |
| `adapter_id` / `adapter_version` | Required for adapted output; stable for native serialization adapters. |
| `native_binding` | Provider-owned paths, keys, events, matchers, payload and serialization. |
| `target_scopes` / `native_precedence` | Exact supported scopes and provider-native winning order. |
| `activation` | Trust, restart/session and runtime prerequisite evidence. |
| `security_mapping` | Mapping of all three common security axes; no combined autonomy boolean. |
| `ownership` | P2 artifact/boundary/lock plan and action policy. |
| `diagnostic` | Stable unsupported/untrusted/missing-mapping next action. |

Claude Code and Codex projections MUST render independently from the common catalog. The
Claude projection preserves current committed preset discovery, merge-only behavior, hook
registrations, agent-pack lock/upgrade categories and named settings audit. The Codex
projection uses native configuration, trust, approval, sandbox, hooks/context, MCP and agent
surfaces only where first-party capability evidence and the projection mapping support them.

Low-level bindings are legal only inside `native_binding`. Illustrative projection-only
bindings include `.claude/settings.json`, `.codex/config.toml`, `PreToolUse`,
`approval_policy` and `sandbox_mode`; none is a common Profile/Surface field. An unsupported
event or target remains `unsupported` with a diagnostic and is never silently emulated by a
wrapper/polling loop.

Projection changes require mapping provenance: current first-party source or committed
repo-grounded adapter evidence, verification date, scope and claim. Unknown mapping version,
missing evidence or stale source hash fails closed.

## Managed ownership

Every rendered provider artifact is governed by the frozen artifact contract. Its record
contains stable artifact identity, ordered canonical sources, provider/surface/profile IDs,
adapter identity/version, capability requirements, target path, source/rendered hashes,
override provenance and `whole-file` or `managed-blocks` ownership.

Rules:

- `plan`, `check`, `doctor` and `dry-run` are strictly no-write, including targets, locks,
  backups and config carriers.
- Existing unowned targets are `ownership-conflict`; they are not adopted or overwritten.
- Merge/update changes only a matching managed boundary and preserves user-owned values/bytes.
- `managed-drift` requires explicit repair with expected/observed hashes and recoverable
  pre-image. Update cannot repair drift.
- Invalid/corrupt/newer provenance, duplicate markers or ownership ambiguity refuses before
  write.
- Remove deletes only matching manager-owned bytes. User-owned/local-modified content stays.
- One Provider's success cannot hide another required projection failure; aggregate remains
  non-green.

Legacy Claude agent-pack locks remain compatibility inputs until the P5 implementation
projects them through P2 provenance. They are not a source for Codex output and do not grant
ownership of an untracked target.

## Secrets

A common record contains only a `secret_ref` identity and an activation requirement. It MUST
NOT contain a resolved value, token, credential, private key, host-secret path or captured
environment value.

Provider projections may serialize a provider-native reference/placeholder, never the value.
Locks, hashes, reports, diagnostics, fixtures, backups and generated docs MUST be value-free.
Render/check validates that every required reference has a unique provider mapping. Runtime
availability is checked only at the declared activation boundary and reported with redacted
identity. Missing/ambiguous reference is `HARNESS_SECRET_REFERENCE_MISSING`; evidence of a
resolved value in any artifact is `HARNESS_SECRET_VALUE_EXPOSED` and blocks publication/write.

## Diagnostics

Every diagnostic contains `severity`, `code`, `provider_id`, `profile_id`, `surface_id`,
`target_scope`, `path`, `required`, `observed`, `provenance`, `message` and `next_action`.
Message may be localized; the other fields are stable/machine-readable.

| Code | Condition and required outcome |
|:--|:--|
| `HARNESS_ID_INVALID` | Unknown/duplicate/path-derived profile or surface identity; refuse before render. |
| `HARNESS_CATALOG_MISMATCH` | Missing/extra/duplicate catalog/projection member; no write. |
| `HARNESS_VERSION_UNSUPPORTED` | Unknown contract/catalog/mapping major or unsupported minor; no fallback. |
| `HARNESS_PROVIDER_DISABLED` | Effective provider is disabled; no projection or activation. |
| `HARNESS_CAPABILITY_UNSUPPORTED` | Required capability/support level is unavailable; required profile blocks. |
| `HARNESS_MAPPING_MISSING` | Provider security/surface/target binding missing or ambiguous; no nearest mapping. |
| `HARNESS_TRUST_REQUIRED` | Native activation trust prerequisite unsatisfied; no activation/write. |
| `HARNESS_FULL_ACCESS_EXPLICIT_REQUIRED` | Full access requested without exact operation/target; refuse. |
| `HARNESS_FULL_ACCESS_INHERITANCE_FORBIDDEN` | Full access appears in default/project/fleet/legacy input; refuse before render. |
| `HARNESS_SCOPE_UNSUPPORTED` | Requested project/user/managed scope unavailable or ambiguous; no write. |
| `HARNESS_SECRET_REFERENCE_MISSING` | Required reference/mapping absent; no write/activation. |
| `HARNESS_SECRET_VALUE_EXPOSED` | Resolved secret found in artifact/lock/report/fixture; block and redact evidence. |
| `HARNESS_OWNERSHIP_CONFLICT` | Target/lock/boundary is unowned, corrupt or belongs to another artifact; refuse. |
| `HARNESS_MANAGED_DRIFT` | Managed bytes differ; ordinary update refuses, explicit repair required. |
| `HARNESS_USER_OWNED_CONFLICT` | Proposed merge/repair would replace user-owned value/bytes; preserve and refuse. |
| `HARNESS_ACTIVATION_UNSUPPORTED` | Surface has no safe native activation for this provider; report unsupported, never emulate silently. |

Errors return no partial render plan. Diagnostics remain provider-qualified; a green row for
one selected provider cannot erase another selected provider's error.

## Compatibility

Legacy provider configuration with no explicit provider layer retains Claude Code-only
behavior and does not render/enable Codex or full access. Current Claude preset names,
permission merge, hook registrations/kill switches, MCP merge, agent-pack provenance/upgrade/
remove categories and named settings doctor output remain compatibility gates. Provider
support is additive; compatibility never converts a Claude artifact into a Codex source.

Contract major changes Profile/Surface identity or intent, security axes, full-access rule,
scope/precedence, managed ownership, secret boundary or diagnostic outcome. Minor adds a
compatible profile/surface/projection field or new provider projection. Patch is editorial or
evidence-only. Catalog major removes/renames/narrows an identity; minor adds a profile/surface
or improves explicit support; patch refreshes evidence/diagnostic without semantic change.
Unknown major fails closed.

Provider mapping/adapter versions evolve independently and appear in P2 provenance. Any
change to expected managed bytes changes adapter/source hashes and is `stale-source`, never
an unreported overwrite.

## Golden examples

### G1 — observe is no-write

Selected `observe` returns read/check diagnostics and no executable project lifecycle
activation. Both provider rows are explicit. Unsupported optional surfaces remain visible;
target, lock, backup and config hashes are unchanged.

### G2 — workspace-contained autonomous operation

An explicitly trusted project selects `workspace-contained`; the provider projection maps
non-interactive approval and a workspace-limited sandbox independently. The render plan may
touch only declared managed project targets. External paths/network are not inferred from
the approval choice. Missing trust yields `HARNESS_TRUST_REQUIRED` before write.

### G3 — explicit full access

`trusted-full-access` succeeds only from operation `self-host-apply` with an exact trusted
repository target and a complete provider mapping. The same profile in project, fleet-project,
fleet-default, legacy or missing-origin input yields
`HARNESS_FULL_ACCESS_INHERITANCE_FORBIDDEN`. Omitting operation/target yields
`HARNESS_FULL_ACCESS_EXPLICIT_REQUIRED`.

### G4 — independent provider projections

One semantic `context.plans-directory` Surface renders through each provider's own binding.
The Claude artifact is not parsed to create the Codex artifact. If the Codex mapping is absent,
that provider row is `HARNESS_MAPPING_MISSING` and the aggregate is non-green; Claude output
does not supply a fallback.

### G5 — missing capability or activation

A required lifecycle Surface with unavailable capability is
`HARNESS_CAPABILITY_UNSUPPORTED`; a surface lacking a safe native activation is
`HARNESS_ACTIVATION_UNSUPPORTED`. Neither case creates a shell wrapper or polling emulation.

### G6 — secret reference only

An MCP record refers to `github-token` by identity and provider-native placeholder. Missing
mapping is `HARNESS_SECRET_REFERENCE_MISSING`. A resolved token in rendered bytes, lock,
report or fixture is `HARNESS_SECRET_VALUE_EXPOSED`; no artifact is published.

### G7 — user-owned conflict and repair

An existing unmanaged target or occupied value is `HARNESS_OWNERSHIP_CONFLICT` /
`HARNESS_USER_OWNED_CONFLICT`. Managed drift produces expected/observed hashes but ordinary
update refuses; explicit repair changes only matching managed bytes and preserves the rest.

## Approval

D85 freezes this contract as v1.0.0 through D79 delegated owner approval. The approval is
substantive and atomic:

1. **H1 — identity/catalog:** one stable provider-neutral Profile/Surface catalog and the
   exact initial security profiles/surfaces above;
2. **H2 — independent security:** Trust, Approval and Sandbox axes remain independent;
   workspace-contained autonomy is bounded and full access is explicit-operation-only,
   non-inheritable and target-specific;
3. **H3 — native projections:** provider paths/keys/events/activation live only in named,
   evidenced independent projections; unsupported is diagnostic, not hidden emulation;
4. **H4 — scopes/ownership:** project/user/managed scope and provider-native precedence are
   explicit; P1 selection and P2 provenance/drift/repair remain their frozen SSOTs;
5. **H5 — secrets/diagnostics:** secret references only, stable provider-qualified no-write
   diagnostics and partial-provider non-green aggregation;
6. **H6 — compatibility/goldens:** legacy Claude-only behavior and current Claude surfaces
   remain compatibility gates; security/ownership negative cases are normative;
7. **H7 — authority/consumers:** the contract opens only P5.2–P5.7 implementation/conformance
   and later declared P6/P7 consumers; it authorizes no live/user-global apply, FOREMAN/fleet
   mutation or change to frozen P0–P4 contracts.

Exact delegated approval record:

```text
APPROVE P5.1 HARNESS H1-H7 AS WRITTEN UNDER D79
```

Any semantic change to H1–H7 requires a superseding D# and contract version decision.
