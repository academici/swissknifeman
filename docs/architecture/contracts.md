# Contracts

The contracts that modules exchange, who owns them, how they evolve and where they are still incomplete. The decisions
behind this page are [ADR 0014](decisions/0014-language-neutral-contracts-in-aicore.md) (where contracts live) and
[ADR 0015](decisions/0015-versions-by-dimension-and-stability-stages.md) (how versions and stability work).

JSON Schema is the source of truth of a contract; code implements it. Every schema carries a concrete `$schema` and a
`$id` that ends in `:v<N>`, and `python3 scripts/ecosystem-units.py check` verifies both, and that the `$id` version
equals the version of the directory.

## Inventory

Columns: the contract, its identifier or carrier, the owner module, the stability stage, and the gap with the stage that
is expected to close it. Stages are named in [ecosystem](ecosystem.md#stages).

### Contracts that exist as schemas

| Contract | `$id` / carrier | Owner | Stability | Gap and closing stage |
| --- | --- | --- | --- | --- |
| Module manifest `unit/v1` | `urn:swissknifeman:aicore:unit:v1`, `packages/aicore/schemas/unit/v1` | aicore | development | manifest of external plugins and `permissions` enforcement: P6 |
| Check result `check-result/v1` | `urn:swissknifeman:aicore:check-result:v1`, `packages/aicore/schemas/check-result/v1` | aicore | development | modules still print text in `doctor`; conversion P11, aggregation P12 |
| Orchestration `exec/v1` (nine document kinds) | `urn:swissknifeman:orch:exec:<kind>:v1`, `packages/orch/schemas/exec/v1` | orch | alpha | event identity, causation, epoch, digests and proof: P10 |
| Plan `plan/v1` (plan, phase, item, decision, document, brief, bridge, evidence, log event, snapshot, read envelopes) | `urn:swissknifeman:task:plan:<kind>:v1`, `packages/task/schemas/plan/v1` | planner (task until the rename) | beta | none; the URNs never change |
| Skiller schemas (`evals`, `host`, `swissknife`, `swissknifeman-config`, `upstream`) | `urn:skiller:<kind>:v1`, `packages/skiller/schema` | skiller | beta | draft-07, migrate to 2020-12 when skiller contracts move (stage: content and delivery) |

### Contracts that exist only as data or code

| Contract | `$id` / carrier | Owner | Stability | Gap and closing stage |
| --- | --- | --- | --- | --- |
| Bridge descriptor of planner | `urn:swissknifeman:task:plan:bridge:v1`, `packages/task/bridges/orch/bridge.json` | planner | beta | none; schema is in `plan/v1` |
| Bridge descriptor of orch | `urn:swissknifeman:orch:bridge:v1`, `packages/orch/bridges/*/bridge.json` | orch | alpha | no schema file; unify the two descriptors in the bridges stage: P10 |
| Provider manifests | `configs/provider-capabilities.json`, `provider-distribution.json`, `provider-projection.json` (`schema_version` or `contract_version` `1.0.0`) | aicore (provider) | development | version field only, no JSON Schema; schema with the move into `aicore`: P3 |
| Model catalog | `packages/task/configs/command-routing.json` | aicore (provider) | development | still inside the task package: P3 |

### Inventory of execution contracts

| Contract | Present form | Owner | Gap and closing stage |
| --- | --- | --- | --- |
| ExecutionInput | `exec/v1` `execution-input` | orch | brief as an artifact addressed by digest, compressed optional part: P10 |
| ExecutionPlan | `exec/v1` `launch-plan` (`prepare --dry-run`) | orch | digests, module versions, decisions, proof: P10 |
| RunEvent | `exec/v1` `run-event` (`run_id`, `stage_id`, `attempt`, `seq`, `ts`, `kind`, `data`, `raw_ref`, `route_observed`) | orch | `event_id`, causation and correlation, `owner_epoch`: P10 |
| StageResult / RunResult | `exec/v1` `stage-result` | orch | module versions and skill digest: P10 |
| CapabilityManifest | `exec/v1` `capability-record` | orch, with support levels in aicore | source, freshness, remediation; shared support levels: P3, P10 |
| PluginManifest | `unit.json` | aicore | schema now; manifest of an external plugin: P6 |
| ProviderDescriptor | provider manifest, `configs/provider-capabilities.json` | aicore (provider) | model catalog from command routing: P3 |
| SkillDescriptor | skill frontmatter, `skills.json`, `skills-lock.json` | aicore (content) | license, compatibility, required tools, provenance: P5 |
| HealthCheckDescriptor | `provides.doctor` in `unit.json`, `check-result/v1` | aicore and modules | modules' own `doctor` formats differ: P11, P12 |
| PolicyDecision | refusals `CODE: message`, run-policy | orch | structured decision inside the launch plan: P10 |
| EffectRequest / Receipt | `exec/v1` `effect-receipt` | orch | `effect_id` as idempotency key: P10 |
| Error taxonomy | scattered codes; classes `quota`, `auth`, `timeout` in the engine port | aicore (provider) and modules | one registry of classes and codes: P3 |
| Canonical digest | sha256 of canonical JSON in `exec` and in plan digests | aicore | one implementation: P3 |
| Schema evolution | rule of `exec/v1` | aicore | policy per contract (below) |
| Ecosystem event envelope | `{id, ts, source, type, project, subject, data}` | aicore (ext) | CloudEvents-style fields, envelope apart from data: P6 |
| Check evidence | `exec/v1` `check-evidence`, plan evidence | orch and planner | none |

## Evolution rules

Common to every contract:

- A **minor** change only adds optional fields inside `v<N>`. `$id` stays the same and the change is recorded in the
  changelog of the contract.
- A **major** change creates a new directory `v<N+1>` next to the old one; the old directory stays in place while any
  consumer reads it.
- Schemas of the closed profile reject unknown fields (`additionalProperties: false`); a producer must not write a
  field the schema does not list.
- Compatibility is expressed in separate dimensions: module version (SemVer), manifest version (`$schema` of
  `unit.json`), contract version (`v<N>`), protocol version (`protocol` min and max) and capability version (`id@N`).
- Stability stages are `development`, `alpha`, `beta`, `rc`, `stable`, `deprecated`.
- A shim, alias or reader of an old format has a compatibility window, a removal stage and a test
  ([ADR 0020](decisions/0020-migration-discipline.md)).

For each contract, the table fields below follow [ADR 0015](decisions/0015-versions-by-dimension-and-stability-stages.md):
what consumers read, what producers write, who upcasts, the deprecation window, behaviour on unknown fields and the
migration fixtures. While `v1` is the only major of every contract, consumers read `v1`, producers write `v1`, no
upcast exists and no deprecation window runs; the window of a contract is set, and recorded here, in the same change
that introduces its `v2`.

### unit/v1

| Aspect | Policy |
| --- | --- |
| Reads | consumers read `v1` only (the hub check, later `aicore unit`) |
| Writes | `$schema: urn:swissknifeman:aicore:unit:v1` |
| Upcast | none |
| Deprecation window | set with `v2` |
| Unknown fields | rejected |
| Fixtures | `packages/aicore/schemas/unit/v1/examples/{valid,invalid}`, exercised by `scripts/test-ecosystem-units.py` |

Fields: `$schema`, `id`, `title`, `kind` (`foundation`, `capability`, `bridge`), `version`, `stability`,
`destination` (`own-repo`, `hub`), `requires` (list of `{unit, range}`), `provides` (`cli`, `plugins`, `contracts`,
`doctor`, `config`, `events`, `overlay_slots`, `extension_points`, `ports`), and optional `permissions`, `protocol`,
`dev`. Collections are lists of records, never maps with arbitrary keys, because the closed profile of the validator
cannot express such maps ([ADR 0025](decisions/0025-unit-manifest-shape-and-aicore-skeleton.md)).

### check-result/v1

| Aspect | Policy |
| --- | --- |
| Reads | `v1` only; no module produces it yet |
| Writes | `$schema: urn:swissknifeman:aicore:check-result:v1`, required `check_id`, `status`, `category`, `observed` |
| Upcast | none |
| Deprecation window | set with `v2` |
| Unknown fields | rejected |
| Fixtures | `packages/aicore/schemas/check-result/v1/examples/{valid,invalid}` |

`status` is `ok`, `warn`, `fail` or `skip`; `category` is `environment`, `config`, `state`, `content` or
`integration`. Repair is separate from probing ([ADR 0022](decisions/0022-doctor-as-module-contract.md)).

### exec/v1

| Aspect | Policy |
| --- | --- |
| Reads | `v1` only |
| Writes | `contract_version: "exec/v1"` and the document `$schema` of its kind |
| Upcast | none; a breaking change creates `schemas/exec/v2/` |
| Deprecation window | set with `v2` |
| Unknown fields | rejected |
| Fixtures | `packages/orch/fixtures/exec/v1/{valid,invalid}`; the changelog of the contract is in the orch documentation |

Minor additions so far were optional fields (`run-policy.isolation`, `run-policy.commit`, `stage-result.commits`) and
documents stayed valid. The protocol additions of [ADR 0018](decisions/0018-execution-protocol-identity-fencing-idempotency.md)
are additive in the same way.

### plan/v1

| Aspect | Policy |
| --- | --- |
| Reads | `v1` only; plans in projects must stay readable |
| Writes | `$schema` of the document kind, `urn:swissknifeman:task:plan:<kind>:v1` |
| Upcast | none |
| Deprecation window | set with `v2`; URNs do not change with the module rename |
| Unknown fields | rejected |
| Fixtures | `packages/task/tests/engine/fixtures/{valid,invalid}` and the synthetic demo plans |

### Bridge descriptors (`bridge.json`)

| Aspect | Policy |
| --- | --- |
| Reads | the partner CLI reads the descriptors of its own side |
| Writes | planner: `urn:swissknifeman:task:plan:bridge:v1`; orch: `urn:swissknifeman:orch:bridge:v1` |
| Upcast | none |
| Deprecation window | set when the descriptors are unified |
| Unknown fields | rejected for the planner descriptor (schema in `plan/v1`); the orch descriptor has no schema yet |
| Fixtures | the three orch descriptors and the planner descriptor in the repository |

The descriptor names the partner, the direction, the contract (`exec/v1`, `skiller.resolve/v1`, and so on), the
entrypoints and the required CLI and environment variable. The `protocol` range of `unit.json` is meant for bridges.

### Skiller schemas (`urn:skiller:*`)

| Aspect | Policy |
| --- | --- |
| Reads | `v1` only |
| Writes | `$id` `urn:skiller:<kind>:v1` |
| Upcast | none |
| Deprecation window | set with `v2` |
| Unknown fields | as declared by each schema |
| Fixtures | module tests of `skiller` |

These schemas use draft-07; they are to be migrated to 2020-12 when the skiller contracts move (stage: content and
delivery), after which they follow the closed profile like the others.

### Provider manifests

| Aspect | Policy |
| --- | --- |
| Reads | the provider layer reads the `schema_version` (or `contract_version`) `1.0.0` documents |
| Writes | the same version field; the capability manifest also carries `catalog_version` |
| Upcast | none |
| Deprecation window | none yet; a JSON Schema is added when the provider layer moves into `aicore` |
| Unknown fields | not enforced by a schema today |
| Fixtures | tests of the provider layer; golden fixtures pin the generated output |

A minor change of the catalog raises `catalog_version`; a change of the document shape raises the version field and
is announced in the changelog.
