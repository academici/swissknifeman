# Provider instruction contract

**Version:** v1.0.0 (frozen)

**Basis:** provider capability, configuration and harness contracts v1.0.0 plus artifact contract v1.1.0

## Purpose

This contract defines one provider-neutral instruction canon for the swissknifeman root and
its nine package scopes. `CLAUDE.md` and `AGENTS.md` are independent provider projections of
the same ordered common semantic sections, followed by an explicit provider-extension
section set. Bytes and phrasing may differ; common meaning may not.

The contract fixes schema, ownership, provenance, observation, action, diagnostics and
compatibility. It does not authorize live modification or adoption of any existing instruction
file, fleet mutation, or output-to-output translation.

Normative words `MUST`, `MUST NOT`, `SHOULD` and `MAY` are literal.

## Identity

The contract envelope has these stable identities:

| Identity | Frozen value or rule |
|:--|:--|
| Contract | `provider-instruction-contract` / `1.0.0` |
| Artifact kind | `instruction-projection` |
| Providers | exactly `claude-code`, `codex` |
| Scope IDs | exactly the nine IDs in `Scopes` |
| Artifact ID | `harness.instruction-projection.<scope-id>.<provider-id>` |
| Adapter ID | `harness.instruction.<provider-id>` |
| Managed boundary | `managed-blocks`, exactly two ordered block IDs |
| Lock carrier | `.swissknifeman/provider-artifacts.lock.json` |

Scope and semantic IDs are lowercase dotted identities. Each segment starts with an ASCII
lowercase letter and then contains lowercase letters, digits or hyphens. Provider extension
IDs MUST contain the exact provider ID immediately after the scope owner, for example
`root.codex.bootstrap` or `harness.claude-code.settings-precedence`. A removed identity is
never reused with another meaning.

Target paths are locations, not identities. Moving a target does not silently change its
artifact ID, ownership or semantic inventory; it requires an explicit compatible migration.

## Scopes

The target inventory is closed and explicit. Filesystem discovery and implicit package scans
are forbidden.

| Scope ID | Scope root | Claude Code target | Codex target |
|:--|:--|:--|:--|
| `root` | `.` | `CLAUDE.md` | `AGENTS.md` |
| `skiller` | `packages/skiller` | `packages/skiller/CLAUDE.md` | `packages/skiller/AGENTS.md` |
| `harness` | `packages/harness` | `packages/harness/CLAUDE.md` | `packages/harness/AGENTS.md` |
| `maind` | `packages/maind` | `packages/maind/CLAUDE.md` | `packages/maind/AGENTS.md` |
| `analyst` | `packages/analyst` | `packages/analyst/CLAUDE.md` | `packages/analyst/AGENTS.md` |
| `planner` | `packages/planner` | `packages/planner/CLAUDE.md` | `packages/planner/AGENTS.md` |
| `brain` | `packages/brain` | `packages/brain/CLAUDE.md` | `packages/brain/AGENTS.md` |
| `orch` | `packages/orch` | `packages/orch/CLAUDE.md` | `packages/orch/AGENTS.md` |

A conforming catalog contains all and only these nine scope records and all and only the two
targets per scope. Missing, extra, duplicate, aliased or discovered targets fail before
render. `packages/<name>` is never inferred from directory contents.

## Semantic sections

Each semantic section record contains exactly:

| Field | Contract |
|:--|:--|
| `id` | Stable semantic identity, unique across the catalog. |
| `scope_id` | One exact scope from `Scopes`. |
| `kind` | `common` or `provider-extension`. |
| `provider_id` | `null` for common; exact owner for an extension. |
| `order` | Positive integer unique inside `(scope_id, kind, provider_id)`; ascending render order. |
| `intent` | Provider-neutral observable meaning for common, additive native meaning for extension. |
| `obligations` | Non-empty ordered structured obligations: modality, subject, action, object and boundary. |
| `sources` | Non-empty ordered canonical source records with full SHA-256. |
| `compatibility_assertions` | Ordered rules/commands/links/literals that the projection must preserve. |

Order is catalog data, not Markdown-heading discovery. Reordering an existing ID changes
catalog semantics. Duplicate order, duplicate ID, a missing common ID, an extension in the
common list, or a provider-mismatched extension is invalid.

The initial ordered common inventories are frozen as follows:

| Scope | Ordered common semantic IDs |
|:--|:--|
| `root` | `root.ecosystem-identity` · `root.repository-layout` · `root.package-boundaries` · `root.cli-routing` · `root.shared-core` · `root.marketplace` · `root.engineering-invariants` · `root.plan-lifecycle` · `root.development-validation` · `root.reference-provenance` · `root.decision-verification` · `root.provider-parity` · `root.worktree-safety` · `root.untrusted-content` · `root.evidence-integrity` · `root.generated-artifacts` · `root.speculative-work` · `root.docs-build` · `root.module-folders` · `root.product-philosophy` |
| `skiller` | `skiller.identity` · `skiller.distribution-channels` · `skiller.configuration-ownership` · `skiller.core-policy` · `skiller.layout-and-generation` · `skiller.module-boundaries` · `skiller.engineering-invariants` · `skiller.validation-release` |
| `harness` | `harness.identity` · `harness.semantic-source` · `harness.layout` · `harness.command-surface` · `harness.agent-pack-lifecycle` · `harness.engineering-invariants` · `harness.cross-package-boundaries` · `harness.validation-release` |
| `maind` | `maind.identity` · `maind.three-planes` · `maind.layout` · `maind.module-boundaries` · `maind.orchestration` · `maind.engineering-invariants` · `maind.validation-release` |
| `analyst` | `analyst.identity-human-gate` · `analyst.layer-boundary` · `analyst.layout` · `analyst.module-boundaries` · `analyst.data-lifecycle` · `analyst.privacy` · `analyst.engineering-invariants` · `analyst.validation-release` |
| `planner` | `planner.identity` · `planner.command-catalog` · `planner.plan-protocol` · `planner.plan-files` · `planner.layout` · `planner.schema-ownership` · `planner.engineering-invariants` · `planner.configuration` · `planner.events-and-extensions` · `planner.validation-release` |
| `brain` | `brain.identity` · `brain.layout` · `brain.module-boundaries` · `brain.vault-safety` · `brain.engineering-invariants` · `brain.validation-release` |
| `orch` | `orch.identity` · `orch.module-boundaries` · `orch.engineering-invariants` · `orch.validation-release` |

The initial provider-extension inventories are:

| Scope | `claude-code` ordered extension IDs | `codex` ordered extension IDs |
|:--|:--|:--|
| `root` | `root.claude-code.native-surfaces` · `root.claude-code.context-budget` · `root.claude-code.research-routing` | `root.codex.bootstrap` · `root.codex.launch-and-hook-integrity` · `root.codex.fresh-agent-execution` |
| `skiller` | `skiller.claude-code.marketplace-connect` · `skiller.claude-code.vendor-targets` · `skiller.claude-code.agent-hub` | empty |
| `harness` | `harness.claude-code.config-surfaces` · `harness.claude-code.lifecycle-surfaces` · `harness.claude-code.settings-precedence` | empty |
| `maind` | `maind.claude-code.plugin-and-mcp` · `maind.claude-code.workspace-trust` | empty |
| `analyst` | `analyst.claude-code.capture-surfaces` · `analyst.claude-code.plugin` | empty |
| `planner` | `planner.claude-code.slash-projection` · `planner.claude-code.model-pins` | empty |
| `brain` | empty | empty |
| `orch` | empty | empty |

`empty` is a normative empty ordered set, not a missing record. Its target still carries an
extension managed block so ownership and future compatible additions remain explicit.

### Pinned root common

Root common sections are on demand: no root target carries them, and the repository guides
are read when a task needs them. The exception is the closed set `ROOT_PINNED_COMMON_IDS`
(`harness.instructions`), currently `root.module-folders` and `root.product-philosophy`. A pinned id is projected to the
common block of every root target, for every provider and independent of the provider
projection policy, so a rule that every agent in the repository must see (the module-folder
rule and the product philosophy) is always in its first-turn context. The common block of a root target contains all and
only the pinned ids, in catalog order; package scopes keep the provider projection policy
unchanged. Pinned ids are a subset of the root common inventory and keep their catalog record,
obligations and compatibility assertions like any other common section.

Pinning another root section is a catalog-minor change: add the id to `ROOT_PINNED_COMMON_IDS`,
bump `catalog_version`, update the compatibility fixture from this contract, and verify the
first-turn budget (`skiller budget --first-turn`) before applying the projections.

## Common canon

Common sections are the sole source of rules that apply to both providers in one scope.

1. Every target in a scope MUST project the exact ordered common ID set declared above.
2. Each common record has one normalized obligation set. Provider renderers may alter
   wording, examples and native invocation syntax only while preserving every obligation.
3. A common rule is never copied into an extension record. Provider-neutral package
   identity, source-of-truth boundaries, safety constraints, validation and release rules
   remain common even when current prose mentions one provider.
4. Common sources are explicit catalog/fragments. Existing `CLAUDE.md` or `AGENTS.md` files
   are compatibility inputs and managed targets, never canonical source.
5. Planner command bodies and skill bodies remain in their frozen package canons. Instruction
   fragments may link to them but MUST NOT duplicate or fork their content.
6. A renderer MUST NOT infer meaning from arbitrary Markdown headings or actual output.
   Structured section records and obligations define expected semantics.

Changing a common section's identity, removing or weakening an obligation, or changing its
scope is contract-major unless a separately approved migration preserves old consumers.
Adding an optional common section is contract/catalog-minor and requires both provider
projections in the same release.

## Provider extensions

A provider extension is an additive, explicitly owned native instruction. It MUST satisfy
all of the following before render:

- its ID is in that scope/provider's declared extension list;
- `provider_id` matches its ID namespace and target provider;
- it has its own source fragment, order, intent and structured obligations;
- none of its obligations deletes, weakens, duplicates, shadows or contradicts a common
  obligation;
- it does not claim parity for a provider-native behavior;
- it does not redefine another extension ID or import the other provider's output.

Common obligations are authoritative. There is no precedence rule that lets an extension
win a conflict. A stricter provider-native guard is additive only when it leaves the common
obligation intact and names a narrower native boundary. Duplicate meaning is rejected even
when wording differs: an extension cannot hide a second maintenance copy behind a new ID.

Conflict validation compares structured obligations, not general Markdown. Same
subject/action with opposite modality, broader permission, narrower required coverage,
replacement of a common owner, or an equivalent obligation under another ID emits
`INSTRUCTION_EXTENSION_CONFLICT` and refuses before render or write.

## Projection

For a target `(scope, provider)`, the deterministic input is:

1. this frozen contract and its version;
2. the explicit catalog and catalog version;
3. the ordered common fragment for the scope;
4. the ordered extension fragment for that provider, including an explicit empty fragment;
5. named adapter identity/version and semantic render parameters;
6. capability and effective-provider inputs from the provider capability and configuration contracts.

The Claude Code adapter and Codex adapter each consume that input independently. Translating
`CLAUDE.md` to `AGENTS.md`, translating `AGENTS.md` to `CLAUDE.md`, parsing one rendered file
as source for the other, or refreshing expected inventory from actual output is forbidden.

Each projection renders exactly two blocks in order: common, then provider extension. The
common block contains all and only common IDs in catalog order. The extension block contains
all and only that provider's extension IDs in extension order. Heading style and prose may
differ, but the block metadata/report MUST expose ordered semantic IDs.

Render, plan and conformance are deterministic: identical full source envelope yields
identical managed bytes, source hash, rendered hash and diagnostics. Host path, timestamp,
filesystem order, locale and current target prose are excluded from the source envelope.

## Managed boundaries

Each target uses these stable block IDs and exact marker grammar, where `<scope>` and
`<provider>` are exact IDs from this contract:

```text
<!-- swissknifeman:instructions:<scope>:<provider>:common:begin -->
... common projection ...
<!-- swissknifeman:instructions:<scope>:<provider>:common:end -->

<!-- swissknifeman:instructions:<scope>:<provider>:extension:begin -->
... provider extension projection ...
<!-- swissknifeman:instructions:<scope>:<provider>:extension:end -->
```

The corresponding ordered block IDs are:

1. `instructions.<scope>.<provider>.common`
2. `instructions.<scope>.<provider>.extension`

Markers are exact UTF-8 ASCII literals. Duplicate, missing, nested, overlapping, reordered,
provider-mismatched or scope-mismatched markers are `boundary-invalid`. Inline short hashes
MAY aid human diagnosis but are non-authoritative and MUST NOT replace provenance.

All bytes outside the two exact marker pairs are user-owned and MUST remain byte-for-byte
unchanged by update or repair. The manager owns neither surrounding headings nor the whole
file. A missing target has no outside bytes; an authorized create writes only the two blocks
and one terminating newline.

An existing target without both matching marker pairs and a matching valid lock record is
unmanaged. Plan/check report it; update and repair MUST NOT insert markers, rewrite, merge,
adopt or backfill ownership. Explicit adoption is a separate owner-gated migration with a
recorded pre-image and semantic mapping; it is not implied by provider selection, apply,
update, repair or a nearby legacy marker.

## Provenance and lock

The authoritative carrier is the provider artifact lock
`.swissknifeman/provider-artifacts.lock.json`. Each target has exactly one record. The full
artifact envelope remains mandatory; instruction-specific fields are additive semantic render
parameters carried by the v1.1.0 generic `semantic_metadata` mapping and never replace
identity, source, adapter, hash, boundary, override or capability fields.

The record contains:

| Field | Contract |
|:--|:--|
| `contract_version` | artifact contract version `1.1.0`; old v1.0.0 records remain backward-compatible outside this projection. |
| `artifact_id` | Stable identity. |
| `instruction_contract_version` / `catalog_version` | Versions used for semantic validation. |
| `canonical_sources` | Full ordered source records for contract, catalog, common fragment and provider extension fragment. |
| `adapter_id` / `adapter_version` | Named independent provider adapter. |
| `provider_id` / `target_path` | Exact target identity tuple. |
| `source_hash` | Full deterministic source-envelope SHA-256. |
| `rendered_hash` | Full SHA-256 of the exact two managed blocks, including markers, concatenated in block-ID order. |
| `managed_boundary` | `managed-blocks` and exact two ordered block identities. |
| `override_layers` | Ordered effective provenance; empty in the initial catalog. |
| `capability_requirements` | Provider instruction capabilities and accepted support levels. |
| `semantic_metadata` | Generic v1.1.0 mapping containing `artifact_kind`, instruction/catalog versions, `scope_id`, repeated `provider_id`, ordered `marker_ids`, `block_ids`, `semantic_sections`, `capabilities`, `registry`, and any remaining semantic render parameters. |

Every hash is `sha256:<64 lowercase hex>`. `canonical_sources` includes full content hashes;
the source envelope additionally includes contract/catalog versions, provider/scope/target,
adapter identity/version, ordered semantic IDs, markers, capabilities, overrides and render
parameters. A short inline content hash, Git revision, mtime or rendered hash alone is not
source provenance.

Normative shape:

```json
{
  "schema_version": 1,
  "records": [
    {
      "contract_version": "1.1.0",
      "artifact_id": "harness.instruction-projection.planner.codex",
      "canonical_sources": [
        {"source_id": "instruction.catalog", "path": "packages/harness/configs/common/instructions/catalog.json", "hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
        {"source_id": "instruction.contract", "path": "packages/harness/docs/reference/provider-instruction-contract.md", "hash": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
        {"source_id": "instruction.fragment.planner.codex", "path": "packages/harness/configs/common/instructions/packages/planner/codex.md", "hash": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"},
        {"source_id": "instruction.fragment.planner.common", "path": "packages/harness/configs/common/instructions/packages/planner/common.md", "hash": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"}
      ],
      "adapter_id": "harness.instruction.codex",
      "adapter_version": "1.0.0",
      "provider_id": "codex",
      "target_path": "packages/planner/AGENTS.md",
      "source_hash": "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "rendered_hash": "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
      "managed_boundary": {
        "mode": "managed-blocks",
        "block_ids": [
          "instructions.planner.codex.common",
          "instructions.planner.codex.extension"
        ]
      },
      "semantic_metadata": {
        "artifact_kind": "instruction-projection",
        "block_ids": [
          "instructions.planner.codex.common",
          "instructions.planner.codex.extension"
        ],
        "capabilities": ["instructions.project"],
        "catalog_version": "1.0.0",
        "instruction_contract_version": "1.0.0",
        "marker_ids": [
          "swissknifeman:instructions:planner:codex:common",
          "swissknifeman:instructions:planner:codex:extension"
        ],
        "provider_id": "codex",
        "registry": "explicit",
        "scope_id": "planner",
        "semantic_sections": {
          "common": [
            "planner.identity",
            "planner.command-catalog",
            "planner.plan-protocol",
            "planner.plan-files",
            "planner.layout",
            "planner.schema-ownership",
            "planner.engineering-invariants",
            "planner.validation-release"
          ],
          "provider_extension": []
        }
      },
      "override_layers": [],
      "capability_requirements": [
        {"id": "instructions.project", "accepted_levels": ["native", "adapted"]}
      ]
    }
  ]
}
```

Lock records are validated as an exact target set. Missing, duplicate, foreign, corrupt,
unsupported-major/newer-unsupported-minor, target-mismatched or marker-mismatched records
are non-green and no-write. An inline marker never repairs or creates a lock record.

## Parity

Semantic parity for one scope is true only when:

- the Claude and Codex common ID sets are identical to the frozen exact set;
- their common IDs occur in identical order;
- each ID projects the identical structured obligation set and compatibility assertions;
- every extension is present only in its declared provider set and block;
- extension conflict and duplicate-meaning sets are empty;
- provenance binds each projection independently to the common and own extension sources.

Parity does not require byte, heading, paragraph, example or native-command identity. It
also does not allow lowest-common-denominator deletion. A provider limitation remains an
explicit extension/diagnostic while the common rule stays intact, or the projection is
non-conforming.

The independent conformance reader builds expected sets from this contract, the catalog and
pre-change compatibility inventory. Provider render output cannot define or update expected
sets. Reports expose `missing`, `extra`, `duplicates`, `order_mismatches`,
`extension_conflicts` and `compatibility_mismatches` per scope/provider.

## Drift and repair

Semantic validation runs before artifact observation. A missing/duplicate semantic ID,
invalid order or extension conflict emits its exact diagnostic and `refuse`; it never reaches
a writable plan.

For a semantically valid expected projection, classification follows this priority:
capability → target existence → ownership → provenance → boundary → managed bytes → source
envelope → `clean`.

| Observation | Exact condition | Allowed plan/action | Write boundary |
|:--|:--|:--|:--|
| `missing` | Required target absent and no conflicting lock record exists. | plan/check: report `create`; apply/update: create only with explicit target authorization. | New file: exactly two blocks; lock committed atomically. |
| `clean` | Expected/observed identity, lock, markers, managed bytes, source and render hashes match. | `noop` | no write, including lock/backup/mtime |
| `stale-source` | Valid ownership/provenance/boundary; observed managed bytes match recorded rendered hash; expected source hash changed. | `update` | replace only two managed blocks and matching lock record; preserve outside bytes |
| `managed-drift` | Valid ownership/provenance/boundary; observed managed bytes differ from recorded/expected rendered hash. | ordinary update `refuse`; explicit `repair` | matching blocks only, after diff + recoverable pre-image |
| `boundary-invalid` | Matching artifact identity exists but markers are missing, duplicate, nested, overlapping, reordered or mismatched. | `refuse` | no write; repair cannot guess boundaries |
| `provenance-invalid` | Matching lock/header is malformed, hash-invalid, contract/catalog/adapter unsupported, corrupt, or newer than supported. | `refuse` | no write; no lock backfill |
| `ownership-conflict` | Existing target lacks the matching marker+valid-lock pair, belongs to another artifact, or matching lock points elsewhere. | `refuse` | no write; never implicit adoption |

`plan` and `check` are strictly no-write: targets, locks, backups, config, mtime and project
state remain unchanged. `check` is green only when every required target is `clean`; missing
package AGENTS targets are visible non-green observations.

`update` writes only an explicitly authorized `missing` create or `stale-source` update. It
MUST NOT repair drift, invalid boundaries/provenance or ownership conflict. `repair` writes
only `managed-drift`, requires an explicit operation, expected/observed hashes, a displayed
managed diff and recoverable pre-image, and preserves every outside byte. It MUST NOT create,
adopt, change marker identity, repair a lock guess or rewrite compatibility fixtures.

Target and lock changes are one logical transaction. A partial failure remains non-clean
until a new check proves both. One target/provider success cannot hide another required
failure; aggregate remains non-green.

Explicit adoption, when later authorized, is a separate migration action. Its plan records
the Owner D#, exact pre-image hash, source-to-semantic mapping, outside-byte preservation and
rollback. It is exercised only in temporary fixtures; live self-host adoption stays separately
owner-gated.

## Backward compatibility

The six committed `CLAUDE.md` files are the initial Claude compatibility inventory, not the
new common source. Their required rules, commands, links and literals are captured
independently (`tests/fixtures_data/instruction-compatibility-v1.json`) and bound to exactly
one common or `claude-code` extension ID.

Compatibility requires semantic preservation of:

- root ecosystem/package identity, CLI routing, stdlib-only/shared-core boundaries,
  marketplace provenance, plan lifecycle, validation commands, context-budget gate and
  external-verification rule;
- skiller channel/config/CORE policy, generated-output ownership, bilingual skill flow,
  registry/validation commands and Claude marketplace/vendor/hub specifics;
- harness source/catalog, CLI and agent-pack lifecycle, merge-only/backups, cross-package
  state boundaries, validation, and Claude settings/hooks/MCP/agent-pack specifics;
- maind three-plane/namespace model, orchestration/module boundaries, stdlib/atomic/graph
  invariants, validation, and Claude plugin/MCP/workspace specifics;
- analyst on-demand/human gate, layer/privacy/data/audit invariants, validation, and Claude
  capture/plugin specifics;
- planner plugin-only command/plan protocol, schema ownership, model/effort policy, validation,
  and Claude slash-command projection specifics.

Root `AGENTS.md` is an existing Codex extension/compatibility input but is unmanaged until
the exact markers and lock are created by an explicit migration. Its bootstrap, trusted
launch/hook integrity and fresh-agent execution rules map to the frozen root Codex extension
IDs and MUST NOT be lost.

The five package `AGENTS.md` paths are absent in the initial inventory. Each absence is
normatively `missing`, emits `INSTRUCTION_TARGET_MISSING`, makes check non-green and performs
no write. An explicitly authorized apply may create it only while the path remains absent.
If any path appears before apply without matching markers+lock, classification changes to
`ownership-conflict`; its bytes are never adopted as the planned missing target.

Legacy managed markers such as `swissknifeman:hub` or `maind:healthcheck` do not match this
contract and grant no instruction-projection ownership. They remain outside these blocks and
user/legacy-manager owned unless a separate approved migration says otherwise.

## Diagnostics

Every diagnostic contains these stable fields:

```json
{
  "severity": "error",
  "code": "INSTRUCTION_EXTENSION_CONFLICT",
  "scope_id": "root",
  "provider_id": "codex",
  "target_path": "AGENTS.md",
  "artifact_id": "harness.instruction-projection.root.codex",
  "observation": "semantic-conflict",
  "semantic_id": "root.codex.bootstrap",
  "expected": "common obligation remains authoritative",
  "observed": "extension weakens common obligation",
  "next_action": "revise extension source or obtain a superseding contract decision",
  "message": "localized human-readable text"
}
```

All fields except `message` are machine-readable and mandatory; unavailable values use
`null`, never omission. Diagnostics are ordered by scope order, provider order
`claude-code`,`codex`, target path, semantic order, code.

| Code | Exact condition and outcome |
|:--|:--|
| `INSTRUCTION_SCOPE_INVALID` | Unknown/duplicate/discovered scope or target; refuse. |
| `INSTRUCTION_TARGET_SET_MISMATCH` | Missing/extra/duplicate target record; refuse. |
| `INSTRUCTION_SEMANTIC_ID_MISSING` | Required common/extension ID absent; refuse before render. |
| `INSTRUCTION_SEMANTIC_ID_DUPLICATE` | ID or normalized obligation duplicated; refuse before render. |
| `INSTRUCTION_SEMANTIC_ORDER_INVALID` | Ordered ID set differs from catalog; refuse. |
| `INSTRUCTION_EXTENSION_ID_INVALID` | Extension namespace/owner/set invalid; refuse. |
| `INSTRUCTION_EXTENSION_CONFLICT` | Extension deletes, weakens, duplicates, shadows or contradicts common; refuse. |
| `INSTRUCTION_TARGET_MISSING` | Required path absent; check non-green, no write. |
| `INSTRUCTION_OWNERSHIP_CONFLICT` | Existing path lacks matching markers+valid lock or has foreign identity; refuse. |
| `INSTRUCTION_BOUNDARY_INVALID` | Marker boundary malformed/mismatched/reordered; refuse. |
| `INSTRUCTION_PROVENANCE_INVALID` | Lock/source/adapter/hash record corrupt, unsupported or newer than reader; refuse. |
| `INSTRUCTION_STALE_SOURCE` | Managed bytes clean against lock but expected source hash changed; update eligible. |
| `INSTRUCTION_MANAGED_DRIFT` | Local managed bytes differ; update refuses, explicit repair required. |
| `INSTRUCTION_PARITY_MISMATCH` | Common ID/order/obligation set differs by provider; refuse. |
| `INSTRUCTION_COMPATIBILITY_MISMATCH` | Initial Claude/Codex required assertion missing or changed; refuse. |
| `INSTRUCTION_WRITE_FORBIDDEN` | A no-write operation or out-of-bound write was attempted; abort aggregate. |

No diagnostic downgrades another target's failure. Unknown codes or observation values fail
closed for a writer.

## Golden examples

These outcomes are normative and MUST be tested from contract-authored fixtures, not updated
from actual render output.

### Positive — independent semantic parity

The `planner` common fragment projects its seven ordered common IDs independently to
`packages/planner/CLAUDE.md` and `packages/planner/AGENTS.md`. The Claude extension block contains
its two declared extension IDs; the Codex extension block is present and empty. Phrasing may
differ. Parity is green because common IDs, order and obligations match and both lock records
bind their own source fragment and renderer.

### Positive — outside bytes survive update and repair

A user heading before the common marker and a local note after the extension marker remain
byte-identical across stale-source update and explicit managed-drift repair. Only the two
managed blocks and matching lock record change.

### Negative — extension override

Common obligation says package validation MUST run before release. A Codex extension says it
MAY be skipped for documentation changes. Different ID and provider wording do not help: it
weakens the same subject/action/boundary. Outcome is
`INSTRUCTION_EXTENSION_CONFLICT`, `refuse`, no target/lock/backup write.

### Negative — missing or duplicate semantic ID

Claude omits `root.shared-core`, or Codex emits `root.shared-core` twice under two headings.
Outcomes are respectively `INSTRUCTION_SEMANTIC_ID_MISSING` and
`INSTRUCTION_SEMANTIC_ID_DUPLICATE`; render/apply refuse before artifact classification.

### Negative — unmanaged existing path

`packages/planner/AGENTS.md` exists with useful user prose but has no exact instruction markers
and no matching lock. Outcome is `ownership-conflict` /
`INSTRUCTION_OWNERSHIP_CONFLICT`. Check and plan are no-write; update and repair refuse;
the useful prose is untouched and not implicitly adopted.

### Negative — local managed drift

Both marker pairs and lock are valid, but a user edits one line inside the common block.
Observed managed hash differs from the recorded hash. Outcome is `managed-drift` /
`INSTRUCTION_MANAGED_DRIFT`; update refuses. Only explicit repair with diff, hashes and
recoverable pre-image may restore the blocks.

### Negative — stale source hash

Observed managed bytes still match the lock's rendered hash, while the catalog/common
fragment or adapter version changes the expected source hash. Outcome is `stale-source` /
`INSTRUCTION_STALE_SOURCE`; update may replace only the managed blocks and matching record.

### Negative — corrupt or newer lock

The record has malformed JSON/hash or an unsupported artifact/instruction contract version.
Outcome is `provenance-invalid` / `INSTRUCTION_PROVENANCE_INVALID`; check is non-green and
update/repair refuse without reconstructing provenance from target bytes.

### Negative — missing package AGENTS

`packages/analyst/AGENTS.md` is absent. Outcome is `missing` /
`INSTRUCTION_TARGET_MISSING`; check remains no-write/non-green. An explicitly authorized
apply may create exactly the two blocks plus lock only if the path is still absent.

## Consumer API

All consumers share one semantic API; provider CLIs may wrap it but MUST preserve
the request/result fields and operation boundaries.

| Operation | Input | Result | Mutation contract |
|:--|:--|:--|:--|
| `plan` | explicit scope/provider set, effective provider config/capabilities, target root, operation authorization | ordered expected artifacts, observations, diagnostics, proposed actions and hashes | none |
| `check` | same inputs plus observed target/lock state | ordered per-target report and aggregate green/non-green | none |
| `apply` | a fresh validated plan plus explicit target authorization | per-target create/update/noop results, pre/post hashes and aggregate status | only authorized `missing` create or `stale-source` update |
| `repair` | fresh managed-drift report, explicit repair authorization, diff/pre-image destination | per-target repair result and pre/post hashes | matching managed blocks+record only |

Every request carries `contract_version`, `catalog_version`, `operation_id`, explicit
`scope_ids`, explicit `provider_ids`, `target_root`, effective config provenance and
authorization provenance. Every target result carries `artifact_id`, scope/provider/path,
ordered semantic IDs, observation, action, source/render hashes, marker/block IDs,
diagnostics and `changed`.

Rendering and the API are exercised against temporary targets only; deployment composes the same
plan/check/apply/repair results and never reinterprets states. Release evidence uses the same API and
adds no schema, marker grammar, hash, observation or repair rule.

An explicit adoption migration is not ordinary `apply`. It requires a separately authorized
plan/result carrying Owner decision, pre-image hash, semantic mapping, preserved outside
bytes and rollback. A consumer that lacks this mode returns
`INSTRUCTION_OWNERSHIP_CONFLICT`; it does not approximate adoption with update or repair.
