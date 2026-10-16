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
| Check result `check-result/v1` | `urn:swissknifeman:aicore:check-result:v1`, `packages/aicore/schemas/check-result/v1` | aicore | development | `maind`, `analyst`, `harness`, `skiller` and `brain` print it from `doctor --json`; `swissknifeman doctor` aggregates it ([ADR 0073](decisions/0073-doctor-aggregator.md)) |
| Plugin catalog `plugin-catalog/v1` | `urn:swissknifeman:aicore:plugin-catalog:v1`, `packages/aicore/schemas/plugin-catalog/v1`; skiller's file is `packages/skiller/.claude-plugin/catalog.json` | aicore (content) | development | the document key is `schema` (other aicore contracts use `$schema`); `skills[]` paths are relative to the module ([ADR 0075](decisions/0075-marketplace-from-unit-json.md)) |
| Compat manifest `compat-manifest/v1` | `urn:swissknifeman:aicore:compat-manifest:v1`, `packages/aicore/schemas/compat-manifest/v1` | aicore (release) | development | `compat.json` of `swissknifeman release bundle` ([ADR 0077](decisions/0077-release-bundle.md)) |
| Umbrella config `umbrella-config/v1` | `configs/umbrella.json`, schema `configs/umbrella.schema.json` | hub | development | aliases with ordered routes; the only data in the hub that names modules ([ADR 0072](decisions/0072-umbrella-reads-modules-from-unit-json.md)) |
| Install profiles `install-profiles/v1` | `configs/install-profiles.json`, schema `configs/install-profiles.schema.json` | hub | development | profiles `minimal`, `standard`, `full` ([ADR 0074](decisions/0074-install-profiles.md)) |
| Umbrella output `umbrella-units/v1`, `umbrella-doctor/v1`, `umbrella-install/v1` | output of `swissknifeman units|doctor|install --json` (`units` carries `hub_root`); schemas `configs/schemas/umbrella-units.schema.json` and `umbrella-doctor.schema.json` | hub | development | no schema yet for the install document |
| Digest `digest/v1` | `urn:swissknifeman:aicore:digest:v1`, `packages/aicore/schemas/digest/v1` | aicore | development | `exec` and plan digests still use the bare-hex form and their own copies; they adopt it with their modules: P9, P10 |
| Error `error/v1` | `urn:swissknifeman:aicore:error:v1`, `packages/aicore/schemas/error/v1` | aicore (provider) | development | orch and the engines adopt the classes: P10 |
| Capability support `capability-support/v1` | `urn:swissknifeman:aicore:capability-support:v1`, `packages/aicore/schemas/capability-support/v1` | aicore (provider) | development | the record of `exec/v1` `capability-record` adopts it: P10 |
| Model catalog `model-catalog/v1` | `urn:swissknifeman:aicore:model-catalog:v1`, `packages/aicore/schemas/model-catalog/v1`, data `packages/aicore/configs/model-catalog.json` | aicore (provider) | development | planner reads a generated snapshot in `command-routing.json` (done in P9, [ADR 0053](decisions/0053-planner-engine-without-hard-aicore-dependency.md)); readers move: orch P10, harness P11 |
| Config explain `config-explain/v1` | `urn:swissknifeman:aicore:config-explain:v1`, `packages/aicore/schemas/config-explain/v1` | aicore (config) | development | none yet; modules adopt `aicore.config.resolve` with their own section schemas: P8 to P11 |
| Skill descriptor `skill-descriptor/v1` | `urn:swissknifeman:aicore:skill-descriptor:v1`, `packages/aicore/schemas/skill-descriptor/v1` | aicore (content) | development | none yet; the receipt of skill digests in a run is P10 ([ADR 0038](decisions/0038-skill-descriptor-agent-skills-standard.md)) |
| Skill selection `skill-selection/v1` | `urn:swissknifeman:aicore:skill-selection:v1`, `packages/aicore/schemas/skill-selection/v1` | aicore (content) | development | `selection.json` beside `SKILL.md`; `skiller registry` writes it to `skills.json` (`selection`), `skiller selection` checks it (PLAN4 P8.1, D10) |
| Eval context `eval-context/v1` | `urn:swissknifeman:aicore:eval-context:v1`, `packages/aicore/schemas/eval-context/v1` | aicore (content) | development | none yet; benchmarks carry it as `context` in `skill-benchmark/v3` and `system-bank-benchmark/v2` ([ADR 0039](decisions/0039-eval-result-context.md)) |
| Skiller config `skiller` section | `urn:swissknifeman:skiller:config:v1`, `packages/skiller/configs/config.schema.json` | skiller | development | tables `[skiller]` and `[skiller.sync]` of `.swissknifeman/config.toml`; the legacy files are read with a warning until `swissknifeman upgrade` ([ADR 0050](decisions/0050-skiller-settings-in-the-layered-config.md)) |
| Maind config `maind` section | `urn:swissknifeman:maind:config:v1`, `packages/maind/configs/config.schema.json` | maind | alpha | table `[maind]` of the layered config; the fleet registry is `<state>/maind/registry.json` and is not a layered section ([ADR 0065](decisions/0065-maind-configuration-and-state.md)) |
| Harness config `harness` section | `urn:swissknifeman:harness:config:v1`, `packages/harness/configs/config.schema.json` | harness | alpha | tables `[harness.hooks.<hook>]` (with `providers.<id>`) and `[harness] policy_profile` ([ADR 0067](decisions/0067-harness-configuration-and-state.md)) |
| Analyst config `analyst` section | `urn:swissknifeman:analyst:config:v1`, `packages/analyst/configs/config.schema.json` | analyst | alpha | table `[analyst]`: recompute and digest thresholds |
| Provider selection `[aicore.providers]` | `packages/aicore/configs/config.schema.json`, key `aicore.providers` | aicore (provider) | development | `contract_version` and `[aicore.providers.selection.<provider>]` in the project layer; read by `maind` and `harness` (the legacy `.swissknife.json#/providers` is read with a warning until upgrade) |
| GUI contracts `contribution/v1`, `view-data/v1`, `catalog/v1`, `api-error/v1`, `bootstrap/v1`, `run/v1`, `stream/v1`, `trust/v1`, `config-mutation/v1` | `urn:swissknifeman:gui:<contract>:v1`, `packages/gui/schemas/` (`provides.gui` of `unit/v1` and `extension/v1` names a `gui.json`) | gui | development | frozen before the local API exists; bridges `gui-<module>` adopt `contribution/v1` from P2, the API serves the runtime contracts from P2 ([ADR 0082](decisions/0082-gui-declarative-contributions.md), [ADR 0083](decisions/0083-gui-local-api-security.md)) |
| Run lookup `run-lookup/v1`, `run-codegraph/v1` | `urn:swissknifeman:analyst:run-lookup:v1`, `urn:swissknifeman:analyst:run-codegraph:v1`, `packages/analyst/schemas/` | analyst | alpha | output of `analyst runs show|codegraph --json`; read by `maind analyze` and the code graph report through `aicore.util.partners` ([ADR 0064](decisions/0064-run-analytics-in-analyst-and-event-subscriber.md)) |
| Harness data for maind `mcp-catalog/v1`, `profile-resolution/v1`, `codex-lifecycle/v1`, `instruction-scopes/v1` | `urn:swissknifeman:harness:<name>:v1`, `packages/harness/schemas/<name>/v1` | harness | alpha | output of `harness mcp catalog`, `profiles resolve`, `hooks codex-lifecycle fragment|validate` and `instructions scopes`, all with `--json` ([ADR 0066](decisions/0066-maind-harness-link-and-mcp-projection.md)) |
| Hook state `hooks-state/v1` | `urn:swissknifeman:harness:hooks-state:v1`, `packages/harness/schemas/hooks-state/v1` | harness | alpha | output of `harness hooks show|sync --json` |
| MCP tools `mcp-tools/v1` | `urn:swissknifeman:maind:mcp-tools:v1`, `packages/maind/schemas/mcp-tools/v1` | maind | alpha | output of `maind mcp tools --json` (`tools_digest`, `tools`) ([ADR 0070](decisions/0070-maind-mcp-protocol-negotiation.md)) |
| Projects list `projects-list/v1` | `urn:swissknifeman:maind:projects-list:v1`, `urn:swissknifeman:skiller:projects-list:v1` | maind, skiller | alpha | `maind projects list --json` (registry) and `skiller list --json` (connected projects); each owner has its own schema |
| Common definitions `common/v1` | `urn:swissknifeman:aicore:common:v1`, `packages/aicore/schemas/common/v1` | aicore (ext) | development | none yet; shared `$defs` that other contracts reference; modules adopt them as they add contracts |
| Event `event/v1` | `urn:swissknifeman:aicore:event:v1`, `packages/aicore/schemas/event/v1` | aicore (ext) | development | none yet; journal and delivery are [ADR 0041](decisions/0041-event-envelope-journal-and-delivery.md); the catalog of types is `provides.events` of each `unit.json` |
| Artifact reference `artifact-ref/v1` | `urn:swissknifeman:aicore:artifact-ref:v1`, `packages/aicore/schemas/artifact-ref/v1` | aicore (ext) | development | none yet; points at data stored by `aicore.state.blobs` |
| Permissions `permissions/v1` | `urn:swissknifeman:aicore:permissions:v1`, `packages/aicore/schemas/permissions/v1` | aicore (ext) | development | declared only; enforcement of the profile `read-only` waits for third-party plugins ([ADR 0042](decisions/0042-external-plugin-protocol-and-process-discipline.md)); run-policy adopts it: P10 |
| Extension manifest `extension/v1` | `urn:swissknifeman:aicore:extension:v1`, `packages/aicore/schemas/extension/v1` | aicore (ext) | development | kind `secret-resolver` waits for its first consumer |
| Plugin request `plugin-request/v1` | `urn:swissknifeman:aicore:plugin-request:v1`, `packages/aicore/schemas/plugin-request/v1` | aicore (ext) | development | protocol `1`; no framing or long-lived mode |
| Plugin response `plugin-response/v1` | `urn:swissknifeman:aicore:plugin-response:v1`, `packages/aicore/schemas/plugin-response/v1` | aicore (ext) | development | protocol `1` |
| Plugin describe `plugin-describe/v1` | `urn:swissknifeman:aicore:plugin-describe:v1`, `packages/aicore/schemas/plugin-describe/v1` | aicore (ext) | development | protocol `1`; no cache |
| Telemetry conventions `telemetry-conventions/v1` | `urn:swissknifeman:aicore:telemetry-conventions:v1`, `packages/aicore/schemas/telemetry-conventions/v1` | aicore (ext) | development | names only, no exporter; modules adopt them: P10, P11 ([ADR 0045](decisions/0045-telemetry-naming-conventions.md)) |
| Orchestration `exec/v1` (nine document kinds) | `urn:swissknifeman:orch:exec:<kind>:v1`, `packages/orch/schemas/exec/v1` | orch | alpha | none; minor changes only: event identity, owner epoch, key hierarchy, digests, proof and capability freshness are optional fields recorded in the contract changelog ([ADR 0060](decisions/0060-execution-protocol-fields-in-exec-v1.md)) |
| Work source `work-source/v1` (input, output; operations `claim`, `brief`, `register`) | `urn:swissknifeman:orch:work-source:<kind>:v1`, `packages/orch/schemas/work-source/v1` | orch | alpha | the input of the extension point `orch:work-source`; the plugin of `bridges/planner-orch` writes it ([ADR 0059](decisions/0059-work-source-port-and-evidence-gate.md)) |
| Orch event data `event-data/v1` (one document per `orch.run.*` type) | `urn:swissknifeman:orch:event-data:<type>:v1`, `packages/orch/schemas/event-data/v1` | orch | alpha | none; consumers ignore unknown fields ([ADR 0061](decisions/0061-run-policy-packs-engine-choice-and-orch-events.md)) |
| Orch config `orch` section | `urn:swissknifeman:orch:config:v1`, `packages/orch/configs/config.schema.json` | orch | alpha | table `[orch]` of the layered config: engine, engine by role, default profile, work source, capability freshness, profile folders, events |
| Plan `plan/v1` (plan, phase, item, decision, document, brief, bridge, evidence, log event, snapshot, read envelopes) | `urn:swissknifeman:task:plan:<kind>:v1`, `packages/planner/schemas/plan/v1` | planner | beta | none; the URNs never change; minor additions only ([ADR 0056](decisions/0056-execution-scenario-and-one-owner-per-attempt.md)) |
| Planner config `planner` section | `urn:swissknifeman:planner:config:v1`, `packages/planner/configs/config.schema.json` | planner | beta | table `[planner]` of the layered config, plus the `plan.settings` layer ([ADR 0054](decisions/0054-planner-settings-in-the-layered-config.md)) |
| Planner event data `event-data/v1` (one document per event type) | `urn:swissknifeman:planner:event-data:<type>:v1`, `packages/planner/schemas/event-data/v1` | planner | beta | none; consumers ignore unknown fields ([ADR 0055](decisions/0055-planner-events-overlays-and-external-checks.md)) |
| Planner check plugin `check-plugin/v1` (input, output) | `urn:swissknifeman:planner:check-plugin:<kind>:v1`, `packages/planner/schemas/check-plugin/v1` | planner | beta | none; the input of the extension point `planner:check` ([ADR 0055](decisions/0055-planner-events-overlays-and-external-checks.md)) |
| Skiller schemas (`evals`, `host`, `swissknife`, `swissknifeman-config`, `upstream`) | `urn:skiller:<kind>:v1`, `packages/skiller/schema` | skiller | beta | draft-07, migrate to 2020-12 when skiller contracts move (stage: content and delivery) |

### Contracts that exist only as data or code

| Contract | `$id` / carrier | Owner | Stability | Gap and closing stage |
| --- | --- | --- | --- | --- |
| Bridge descriptor of planner | `urn:swissknifeman:task:plan:bridge:v1`, `bridges/planner-orch/bridge.json` | planner | beta | none; schema is in `plan/v1` |
| Bridge descriptor of orch | `urn:swissknifeman:orch:bridge:v1` | orch | alpha | retired: `orch-skiller` and `orch-harness` are described by their `unit.json` (kind `bridge`) and no longer carry a `bridge.json` |
| Provider manifests | `packages/aicore/configs/provider-capabilities.json`, `provider-distribution.json`, `provider-projection.json` (`schema_version` or `contract_version` `1.0.0`) | aicore (provider) | development | version field only, no JSON Schema; the files moved into `aicore` unchanged and the schema is still open |
| Model catalog snapshot | `mappings.<provider>` in `packages/planner/configs/command-routing.json` | planner | development | generated from the aicore catalog by the projection renderer and verified with `--check`; planner needs it without aicore ([ADR 0053](decisions/0053-planner-engine-without-hard-aicore-dependency.md)) |

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
| HealthCheckDescriptor | `provides.doctor` in `unit.json`, `check-result/v1` | aicore and modules | the hub aggregator `swissknifeman doctor` ([ADR 0073](decisions/0073-doctor-aggregator.md)) |
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
`install`, `doctor`, `config`, `events`, `overlay_slots`, `extension_points`, `ports`), and optional `subscribes` (default event
subscriptions, `<module>:<name>`), `permissions` (`permissions/v1`), `protocol`, `dev`. Collections are lists of records, never maps with arbitrary keys, because the closed profile of the validator
cannot express such maps ([ADR 0025](decisions/0025-unit-manifest-shape-and-aicore-skeleton.md)).

Minor additions of the hub (all optional): `provides.install` (an argv run from the module root; it accepts `--bin-dir DIR`
and `--force`) and, in `provides.plugins[]`, `source` (a plugin folder) or `catalog` (a `plugin-catalog/v1` file) in place
of `manifest`, exactly one of the three ([ADR 0074](decisions/0074-install-profiles.md),
[ADR 0075](decisions/0075-marketplace-from-unit-json.md)).

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
retries; the run policy decides. The optional `evidence` (`structured` | `text`) tells what a classification rests on.
`aicore.provider.errors.classify_signals(provider, signals, now=)` matches normalized signals (`exit_code`,
`fatal_text`, `stderr_tail`, `is_error`, `http_status`, `retry_category`, `api_retries`, `limit_status`,
`limit_window`, `limit_resets_at`, `terminal`; extracted by the orchestrator, never by aicore); a rule's `match` holds
`text_contains_any` (compared with `fatal_text` and `stderr_tail`, case- and apostrophe-folded), `exit_code_any`,
`signal_any` (one of the values) and `signal_not_in` (the signal is present and none of the values); an absent signal makes
a condition false. A rule may set `retry_after_from: limit_resets_at` to date `retry_after_s`. A rule without a primary
source in its test is not added. `capability-support` separates what a provider can do (`feature`) from what is
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

### Event types: planner.* and brain.note.created

The envelope is `event/v1` and the catalog of types is `provides.events` of each `unit.json`. A producer may publish
the schema of the data of each type: planner does, as the multi-document contract `event-data/v1` (one closed schema
per type, `dataschema` of the event is `urn:swissknifeman:planner:event-data:<type>:v1`). Planner emits six types after
the plan lock is released: `planner.plan.created`, `planner.plan.closed`, `planner.phase.closed`,
`planner.item.started`, `planner.item.finished` and `planner.decision.accepted`. Every type carries `plan_id` and
`title`; `short_id` and `repository` are optional; notes, deviation texts and secrets are never in the data. Consumers
ignore unknown fields, so additions are minor. `scripts/test-event-contracts.py` validates every consumer fixture of a
type against the producer schema; when they disagree the consumer fixture is fixed. Two types matter for `brain`:

| Event | Producer | Consumer | Data |
| --- | --- | --- | --- |
| `planner.plan.closed` | planner | `brain:plan-notes` | Required: `plan_id`, `title`, `status` (`done`). Optional: `short_id`, `goal`, `closed_at` (RFC 3339), `repository`, `phases` (`{id, title, status}`) and `counts` (`items`, `done`, `done_with_deviations`, `skipped`, `blocked`). The consumer fixtures in `packages/brain/tests/fixtures/events/planner.plan.closed/` are checked against this schema ([ADR 0048](decisions/0048-plan-closed-subscriber-and-idempotent-notes.md), [ADR 0055](decisions/0055-planner-events-overlays-and-external-checks.md)). |
| `brain.note.created` | brain (`provides.events`) | none yet | `{"note": "<path from the vault root>", "plan_id": "...", "event_id": "..."}`, caused by the closing event. |

### check-result/v1

| Aspect | Policy |
| --- | --- |
| Reads | `v1` only; produced by `doctor --json` of every module that declares `provides.doctor` |
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
| Fixtures | `packages/planner/tests/engine/fixtures/{valid,invalid}`, the synthetic demo plans, `packages/planner/tests/compat/plans/engine-0.28.3` (frozen plans of earlier engines) and `scripts/test-plan-compat.py` (every plan of the repository) |

Changes inside `v1` are minor only: optional fields, same `$id`. The one so far is `orchestration.scenario` (the name of
a run-policy profile, or `solo`); the owner of an attempt needs no field ([ADR 0056](decisions/0056-execution-scenario-and-one-owner-per-attempt.md)).
`aicore schema compat` reads multi-document contracts such as `plan/v1`, `event-data/v1` and `check-plugin/v1`; with
`--root` and `--base-root` it compares a folder with the folder it was renamed from (`packages/task/schemas` before the
rename), so the rename itself shows no breaking change.

### Bridge descriptors (`bridge.json`)

| Aspect | Policy |
| --- | --- |
| Reads | the partner CLI reads the descriptors of its own side |
| Writes | planner: `urn:swissknifeman:task:plan:bridge:v1` (`bridges/planner-orch/bridge.json`, `name` equals the folder name) |
| Upcast | none |
| Deprecation window | none; the bridge verb name changed from `orch` to `planner-orch` without an alias |
| Unknown fields | rejected (schema in `plan/v1`) |
| Fixtures | the planner descriptor in the repository |

The descriptor names the partner, the direction, the contract (`exec/v1`, `skiller.resolve/v1`, and so on), the
entrypoints and the required CLI and environment variable. Only the bridge that the planner dispatches carries a
`bridge.json`; every bridge is a hub unit with a `unit.json` (kind `bridge`, destination `hub`, `protocol` range,
`dev.test`). The planner finds bridge directories through the `bridges.roots` setting; a bridge finds its partners by a
variable or a command on `PATH`, never by a neighbouring path ([ADR 0058](decisions/0058-bridges-as-hub-units-and-partner-lookup.md)).

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
