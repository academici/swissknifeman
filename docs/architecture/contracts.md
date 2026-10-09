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
| Module manifest `unit/v1` | `urn:swissknifeman:aicore:unit:v1`, `packages/aicore/schemas/unit/v1` | aicore | development | `subscribes`, anchored `provides.events`, `overlay_slots` and `permissions` as a `$ref` added as minor changes (P6); `permissions` is declared, not enforced |
| Check result `check-result/v1` | `urn:swissknifeman:aicore:check-result:v1`, `packages/aicore/schemas/check-result/v1` | aicore | development | modules still print text in `doctor`; conversion P11, aggregation P12 |
| Digest `digest/v1` | `urn:swissknifeman:aicore:digest:v1`, `packages/aicore/schemas/digest/v1` | aicore | development | `exec` and plan digests still use the bare-hex form and their own copies; they adopt it with their modules: P9, P10 |
| Error `error/v1` | `urn:swissknifeman:aicore:error:v1`, `packages/aicore/schemas/error/v1` | aicore (provider) | development | orch and the engines adopt the classes: P10 |
| Capability support `capability-support/v1` | `urn:swissknifeman:aicore:capability-support:v1`, `packages/aicore/schemas/capability-support/v1` | aicore (provider) | development | the record of `exec/v1` `capability-record` adopts it: P10 |
| Model catalog `model-catalog/v1` | `urn:swissknifeman:aicore:model-catalog:v1`, `packages/aicore/schemas/model-catalog/v1`, data `packages/aicore/configs/model-catalog.json` | aicore (provider) | development | readers move from `command-routing.json`: planner P9, orch P10, harness P11 |
| Config explain `config-explain/v1` | `urn:swissknifeman:aicore:config-explain:v1`, `packages/aicore/schemas/config-explain/v1` | aicore (config) | development | none yet; modules adopt `aicore.config.resolve` with their own section schemas: P8 to P11 |
| Skill descriptor `skill-descriptor/v1` | `urn:swissknifeman:aicore:skill-descriptor:v1`, `packages/aicore/schemas/skill-descriptor/v1` | aicore (content) | development | none yet; the receipt of skill digests in a run is P10 ([ADR 0038](decisions/0038-skill-descriptor-agent-skills-standard.md)) |
| Eval context `eval-context/v1` | `urn:swissknifeman:aicore:eval-context:v1`, `packages/aicore/schemas/eval-context/v1` | aicore (content) | development | none yet; benchmarks carry it as `context` in `skill-benchmark/v3` and `system-bank-benchmark/v2` ([ADR 0039](decisions/0039-eval-result-context.md)) |
| Skiller config `skiller` section | `urn:swissknifeman:skiller:config:v1`, `packages/skiller/configs/config.schema.json` | skiller | development | tables `[skiller]` and `[skiller.sync]` of `.swissknifeman/config.toml`; the legacy files are read with a warning until `swissknifeman upgrade` ([ADR 0050](decisions/0050-skiller-settings-in-the-layered-config.md)) |
| Common definitions `common/v1` | `urn:swissknifeman:aicore:common:v1`, `packages/aicore/schemas/common/v1` | aicore (ext) | development | none yet; shared `$defs` that other contracts reference; modules adopt them as they add contracts |
| Event `event/v1` | `urn:swissknifeman:aicore:event:v1`, `packages/aicore/schemas/event/v1` | aicore (ext) | development | none yet; journal and delivery are [ADR 0041](decisions/0041-event-envelope-journal-and-delivery.md); the catalog of types is `provides.events` of each `unit.json` |
| Artifact reference `artifact-ref/v1` | `urn:swissknifeman:aicore:artifact-ref:v1`, `packages/aicore/schemas/artifact-ref/v1` | aicore (ext) | development | none yet; points at data stored by `aicore.state.blobs` |
| Permissions `permissions/v1` | `urn:swissknifeman:aicore:permissions:v1`, `packages/aicore/schemas/permissions/v1` | aicore (ext) | development | declared only; enforcement of the profile `read-only` waits for third-party plugins ([ADR 0042](decisions/0042-external-plugin-protocol-and-process-discipline.md)); run-policy adopts it: P10 |
| Extension manifest `extension/v1` | `urn:swissknifeman:aicore:extension:v1`, `packages/aicore/schemas/extension/v1` | aicore (ext) | development | kind `secret-resolver` waits for its first consumer |
| Plugin request `plugin-request/v1` | `urn:swissknifeman:aicore:plugin-request:v1`, `packages/aicore/schemas/plugin-request/v1` | aicore (ext) | development | protocol `1`; no framing or long-lived mode |
| Plugin response `plugin-response/v1` | `urn:swissknifeman:aicore:plugin-response:v1`, `packages/aicore/schemas/plugin-response/v1` | aicore (ext) | development | protocol `1` |
| Plugin describe `plugin-describe/v1` | `urn:swissknifeman:aicore:plugin-describe:v1`, `packages/aicore/schemas/plugin-describe/v1` | aicore (ext) | development | protocol `1`; no cache |
| Telemetry conventions `telemetry-conventions/v1` | `urn:swissknifeman:aicore:telemetry-conventions:v1`, `packages/aicore/schemas/telemetry-conventions/v1` | aicore (ext) | development | names only, no exporter; modules adopt them: P10, P11 ([ADR 0045](decisions/0045-telemetry-naming-conventions.md)) |
| Orchestration `exec/v1` (nine document kinds) | `urn:swissknifeman:orch:exec:<kind>:v1`, `packages/orch/schemas/exec/v1` | orch | alpha | event identity, causation, epoch, digests and proof: P10 |
| Plan `plan/v1` (plan, phase, item, decision, document, brief, bridge, evidence, log event, snapshot, read envelopes) | `urn:swissknifeman:task:plan:<kind>:v1`, `packages/planner/schemas/plan/v1` | planner (task until the rename) | beta | none; the URNs never change |
| Skiller schemas (`evals`, `host`, `swissknife`, `swissknifeman-config`, `upstream`) | `urn:skiller:<kind>:v1`, `packages/skiller/schema` | skiller | beta | draft-07, migrate to 2020-12 when skiller contracts move (stage: content and delivery) |

### Contracts that exist only as data or code

| Contract | `$id` / carrier | Owner | Stability | Gap and closing stage |
| --- | --- | --- | --- | --- |
| Bridge descriptor of planner | `urn:swissknifeman:task:plan:bridge:v1`, `packages/planner/bridges/orch/bridge.json` | planner | beta | none; schema is in `plan/v1` |
| Bridge descriptor of orch | `urn:swissknifeman:orch:bridge:v1`, `packages/orch/bridges/*/bridge.json` | orch | alpha | no schema file; unify the two descriptors in the bridges stage: P10 |
| Provider manifests | `packages/aicore/configs/provider-capabilities.json`, `provider-distribution.json`, `provider-projection.json` (`schema_version` or `contract_version` `1.0.0`) | aicore (provider) | development | version field only, no JSON Schema; the files moved into `aicore` unchanged and the schema is still open |
| Model catalog (transitional copy) | `mappings.<provider>` in `packages/planner/configs/command-routing.json` | planner | development | equal to the aicore catalog (parity test); removed in P9 |

### Inventory of execution contracts

| Contract | Present form | Owner | Gap and closing stage |
| --- | --- | --- | --- |
| ExecutionInput | `exec/v1` `execution-input` | orch | brief as an artifact addressed by digest, compressed optional part: P10 |
| ExecutionPlan | `exec/v1` `launch-plan` (`prepare --dry-run`) | orch | digests, module versions, decisions, proof: P10 |
| RunEvent | `exec/v1` `run-event` (`run_id`, `stage_id`, `attempt`, `seq`, `ts`, `kind`, `data`, `raw_ref`, `route_observed`) | orch | `event_id`, causation and correlation, `owner_epoch`: P10 |
| StageResult / RunResult | `exec/v1` `stage-result` | orch | module versions and skill digest: P10 |
| CapabilityManifest | `exec/v1` `capability-record`; support levels and dimensions in `capability-support/v1` | orch, with support levels in aicore | the record adopts source, freshness and remediation: P10 |
| PluginManifest | `unit.json`; `extension/v1` for an external plugin | aicore | none |
| ProviderDescriptor | provider manifest, `packages/aicore/configs/provider-capabilities.json` | aicore (provider) | model catalog is separate: `model-catalog/v1` |
| SkillDescriptor | `skill-descriptor/v1` (`aicore.content.skill.describe_skill`) over skill frontmatter and `upstream.json`; `skills.json` and `skills-lock.json` keep their formats | aicore (content) | the receipt of skill digests in a run: P10 |
| HealthCheckDescriptor | `provides.doctor` in `unit.json`, `check-result/v1` | aicore and modules | modules' own `doctor` formats differ: P11, P12 |
| PolicyDecision | refusals `CODE: message`, run-policy | orch | structured decision inside the launch plan: P10 |
| EffectRequest / Receipt | `exec/v1` `effect-receipt` | orch | `effect_id` as idempotency key: P10 |
| Error taxonomy | `error/v1`, `aicore.provider.errors`, rules in `packages/aicore/configs/provider-errors.json` | aicore (provider) | the engine port and the modules adopt the classes: P10, P11 |
| Canonical digest | `digest/v1`; implementation `aicore.util.digest` (canonical JSON bytes, tagged sha256, test vectors) | aicore | `exec` and plan digests move onto it: P9, P10 |
| Schema evolution | rule of `exec/v1` | aicore | policy per contract (below) |
| Ecosystem event envelope | `event/v1`, a CloudEvents 1.0 subset (`aicore.ext.events`) | aicore (ext) | none |
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
`doctor`, `config`, `events`, `overlay_slots`, `extension_points`, `ports`), and optional `subscribes` (default event
subscriptions, `<module>:<name>`), `permissions` (`permissions/v1`), `protocol`, `dev`. Collections are lists of records, never maps with arbitrary keys, because the closed profile of the validator
cannot express such maps ([ADR 0025](decisions/0025-unit-manifest-shape-and-aicore-skeleton.md)).

### digest/v1

| Aspect | Policy |
| --- | --- |
| Reads | tagged form `sha256:<64 lowercase hex>`; the bare hex of `exec/v1` is a legacy form named in `$defs.hex` |
| Writes | tagged form only, over the canonical JSON bytes (rules in the schema description) |
| Upcast | none |
| Deprecation window | set with `v2` |
| Unknown fields | not applicable (a string) |
| Fixtures | `packages/aicore/schemas/digest/v1/examples/{valid,invalid}`; test vectors in `vectors.json` |

Canonical JSON: keys sorted by code point, no whitespace, UTF-8 with only the JSON-mandatory escapes, floats
rejected. A change of these rules is a breaking change and creates `digest/v2`. Closed-profile validation of every
aicore schema is `aicore.util.schema`; the hub script `scripts/ecosystem-units.py` uses it.

### error/v1, capability-support/v1, model-catalog/v1

| Aspect | Policy |
| --- | --- |
| Reads | `v1` only; a new class or enum value is a breaking change and creates `v2` |
| Writes | `error`: `class`, `code`, `retryable`, `safe_message` required; `capability-support`: `capability`, `provider`, `dimension`, `level`, `source` required; `model-catalog`: `schema_version`, `catalog_version`, `providers` |
| Upcast | none |
| Deprecation window | set with `v2` |
| Unknown fields | rejected |
| Fixtures | `packages/aicore/schemas/<contract>/v1/examples/{valid,invalid}` |

`error` has twelve classes. `unknown` means the failure could not be classified; it is not the orchestration status
`unknown_outcome` (the request may have been executed). The raw provider text never enters a record: `diagnostic_ref`
points to an artifact. Classification is by data (`provider-errors.json`), and `aicore.provider` neither waits nor
retries; the run policy decides. `capability-support` separates what a provider can do (`feature`) from what is
available now (`resource`), allowed (`policy`) and working (`health`); only a feature can be `unsupported`.

### config-explain/v1 and module config sections

| Aspect | Policy |
| --- | --- |
| Reads | `v1` only; consumers read the output of `aicore config explain <module> --json` |
| Writes | `$schema: urn:swissknifeman:aicore:config-explain:v1`, `module`, `project`, `config_file_version`, `layers`, `entries` |
| Upcast | none |
| Deprecation window | set with `v2` |
| Unknown fields | rejected |
| Fixtures | `packages/aicore/schemas/config-explain/v1/examples/{valid,invalid}` |

Each entry has `key`, `value` (a secret shows its reference), `layer`, `file`, `line`, `source`, `secret`, `default`
and `overridden` (the lower layers that set the key, nearest first). The config file itself is versioned by
`schema_version` (now `1`): a newer value is rejected, a missing one is an error.

A module's section schema is a contract of the module, not of aicore. Its `$id` is `urn:swissknifeman:<id>:config:v1`,
the path is `provides.config` in `unit.json`, and it follows the closed profile plus `minimum`, `maximum` and the
annotations `x-skm-secret` and `x-skm-layers` (a profile extension that older validators ignore only as annotations).
Adding an optional key is a minor change; removing or retyping a key, or narrowing `x-skm-layers`, is a new major
version with the old keys kept readable for the window recorded here. Rules of the layers are in
[ADR 0034](decisions/0034-layered-config-semantics.md).

### Extension contracts: event, artifact-ref, permissions, extension, plugin-*, telemetry-conventions

| Aspect | Policy |
| --- | --- |
| Reads | `v1` only; a reader of `event/v1` ignores unknown scalar extension attributes matching `[a-z0-9]{1,20}` |
| Writes | `$schema: urn:swissknifeman:aicore:<contract>:v1`; plugin documents carry `protocol: "1"` |
| Upcast | none |
| Deprecation window | set with `v2` |
| Unknown fields | rejected, except the extension attributes of `event/v1` |
| Fixtures | `packages/aicore/schemas/<contract>/v1/examples/{valid,invalid}`; journal round trip in `tests/ext/test_event_contract.py` |

All are `development`. Compatibility inside `v1` is checked mechanically by `aicore schema compat`; a breaking change
is an error from `beta` on ([ADR 0043](decisions/0043-validator-profile-and-schema-compatibility.md)). `common/v1` holds
`$defs` only and is referenced from other contracts.

### Event types: planner.plan.closed and brain.note.created

Event types are not schemas of their own: the envelope is `event/v1` and the catalog of types is `provides.events` of
each `unit.json`. Two types matter for `brain`:

| Event | Producer | Consumer | Data |
| --- | --- | --- | --- |
| `planner.plan.closed` | planner (emitted from P9) | `brain:plan-notes` | The consumer's expectation, recorded as fixtures in `packages/brain/tests/fixtures/events/planner.plan.closed/`: `plan_id` and `title` are required; `short_id`, `status`, `goal`, `closed_at` (RFC 3339), `repository`, `phases` (`{id, title, status}`) and `counts` (`items`, `done`, `done_with_deviations`, `cancelled`) are optional; unknown fields are ignored. The schema is made at the source and checked against the fixtures ([ADR 0048](decisions/0048-plan-closed-subscriber-and-idempotent-notes.md)). |
| `brain.note.created` | brain (`provides.events`) | none yet | `{"note": "<path from the vault root>", "plan_id": "...", "event_id": "..."}`, caused by the closing event. |

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
| Fixtures | `packages/planner/tests/engine/fixtures/{valid,invalid}` and the synthetic demo plans |

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

### Skills index fields, host buckets and skiller describe

| Aspect | Policy |
| --- | --- |
| `skills.json` entry | registry-generated; besides `name`, `bucket`, `path` and `requires` it carries `license` (frontmatter, then `upstream.json`, then the package license) and, when the skill declares them, `compatibility` and `allowed_tools`. The new fields are optional, so older readers keep working |
| Host config `bucket_aliases` | object in `configs/skiller-host.json`: bucket name mapped to the list of host plugins whose skills it expands to; applies to buckets marked `"provided_by": "host"` in `buckets.json`. Plugin directories come from `plugin_dirs`; without a host the bucket stays empty and skiller only warns ([ADR 0049](decisions/0049-module-skills-through-host-provided-buckets.md)) |
| `skiller describe SKILL [--json]` | prints `skill-descriptor/v1` ([ADR 0038](decisions/0038-skill-descriptor-agent-skills-standard.md)) of a library or host-module skill; the schema stays with aicore, skiller adds no copy ([ADR 0051](decisions/0051-skill-metadata-in-the-index.md)) |

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
| Reads | `aicore.provider` reads the `schema_version` (or `contract_version`) `1.0.0` documents |
| Writes | the same version field; the capability manifest also carries `catalog_version` |
| Upcast | none |
| Deprecation window | none yet; the files live in `aicore` but still have no JSON Schema |
| Unknown fields | not enforced by a schema today |
| Fixtures | tests of the provider layer; golden fixtures pin the generated output |

A minor change of the catalog raises `catalog_version`; a change of the document shape raises the version field and
is announced in the changelog.
