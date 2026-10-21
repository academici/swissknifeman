# Architecture decision records

Each record states one architecture-level decision of the module ecosystem with its context, the options that were
rejected and the consequences. Records are written once. A decision is changed by a new record that supersedes the
old one, never by editing the old one silently; the old record then gets the status `superseded by NNNN`.

## Format

A record is `NNNN-<slug>.md`, numbered in the order the decisions were taken, 15 to 40 lines, in English, with these
sections:

| Section | Content |
| --- | --- |
| Status | `proposed`, `accepted` or `superseded by NNNN` |
| Context | the question and the facts that forced it |
| Decision | the accepted option, stated so that it can be checked |
| Alternatives considered | rejected options with the reason |
| Consequences | what becomes easier, what becomes mandatory, what is deferred |
| Supersedes | the earlier decisions this one replaces or refines, or `None.` |

Records refer to each other as `ADR NNNN`. Records may only restate the accepted decision and its reasons; a
divergence between the architecture and the code is reported through the working log first and reflected here only
by a new record.

## Index

| Record | Title | Status |
| --- | --- | --- |
| [0001](0001-modules-as-isolated-folders.md) | Modules are isolated folders with a manifest; no new repositories yet | Accepted |
| [0002](0002-module-dependencies-only-on-aicore.md) | A module depends only on its own library and on aicore | Accepted |
| [0003](0003-three-kinds-of-links-and-bridges.md) | Three kinds of links; bridges connect planner and orch | Accepted |
| [0004](0004-aicore-foundation-and-generalisation-boundary.md) | aicore is the foundation, with a strict generalisation boundary | Accepted |
| [0005](0005-layered-config-and-standard-state-locations.md) | Layered configuration and standard state locations | Accepted |
| [0006](0006-extensibility-events-subscriptions-overlays.md) | Extensibility through events, subscriptions, overlays and external commands | Accepted |
| [0007](0007-brain-module-scope.md) | brain is a hub module; only its foundation is in scope | Accepted |
| [0008](0008-skills-live-in-their-module.md) | Only shared skills stay in skiller; module skills move to their module | Accepted |
| [0009](0009-task-renamed-to-planner.md) | task becomes planner, with aliases; plan URNs do not change | Accepted |
| [0010](0010-upgrade-command-and-guide.md) | Transition through swissknifeman upgrade and an upgrade guide | Accepted |
| [0011](0011-toml-for-human-edited-config.md) | TOML for human-edited configuration layers, JSON for generated state | Accepted |
| [0012](0012-planner-configuration.md) | Planner budgets, thresholds and behaviour are configurable | Accepted |
| [0013](0013-orchestration-scenarios-and-prepared-brief.md) | Orchestration scenarios and execution through a prepared brief | Accepted |
| [0014](0014-language-neutral-contracts-in-aicore.md) | Language-neutral contracts live in aicore | Accepted |
| [0015](0015-versions-by-dimension-and-stability-stages.md) | Versions by dimension and stability stages | Accepted |
| [0016](0016-extension-model-levels-and-trust.md) | Extension model: levels, manifest before launch, handshake, trust | Accepted |
| [0017](0017-provider-boundary-and-error-taxonomy.md) | Boundary between aicore.provider and the orch engines; error taxonomy | Accepted |
| [0018](0018-execution-protocol-identity-fencing-idempotency.md) | Execution protocol: event identity, fencing, idempotency, immutable launch plan | Accepted |
| [0019](0019-config-semantics.md) | Configuration semantics: merging, removal, explain, secrets, invocation layer | Accepted |
| [0020](0020-migration-discipline.md) | Migration discipline: golden fixtures, shims with a window, shadow comparison, rollback | Accepted |
| [0021](0021-durable-architecture-docs.md) | Durable architecture documentation and decision records in the repository | Accepted |
| [0022](0022-doctor-as-module-contract.md) | Doctor is a contract of every module | Accepted |
| [0023](0023-releases-and-supply-chain.md) | Releases and supply chain: what is needed now and what waits for a trigger | Accepted |
| [0024](0024-python-package-names.md) | Python package names of modules | Accepted |
| [0025](0025-unit-manifest-shape-and-aicore-skeleton.md) | Shape of unit.json and the aicore skeleton | Accepted |
| [0026](0026-pinned-root-common-instruction.md) | The folder-is-a-module rule through a pinned root common instruction | Accepted |
| [0027](0027-golden-fixtures-lifecycle.md) | Golden fixtures: location, normalisation, lifecycle outside CI | Accepted |
| [0028](0028-aicore-subsystems-and-core-shim.md) | aicore subsystems and the `core` compatibility shim | Accepted |
| [0029](0029-aicore-locator-fragment.md) | Finding aicore through one canonical locator fragment | Accepted |
| [0030](0030-shared-contracts-digest-error-capability-catalog.md) | Shared contracts: digest, error, capability support, model catalog | Accepted |
| [0031](0031-model-catalog-in-aicore.md) | The model catalog belongs to aicore | Accepted |
| [0032](0032-ready-made-or-own-and-non-goals.md) | Ready-made or own: criteria, non-goals, Python 3.9 | Accepted |
| [0033](0033-error-record-context-limit-and-unknown.md) | error/v1: `context_limit`, request identity, `unknown` is not `unknown_outcome` | Accepted |
| [0034](0034-layered-config-semantics.md) | Layered config semantics: schema, file, layers, merge operators, environment, secrets, explain | Accepted |
| [0035](0035-state-locations-legacy-reads-and-backups.md) | State locations, legacy reads and backups | Accepted |
| [0036](0036-toml-vendored-tomli-and-minimal-editor.md) | TOML: vendored tomli and a minimal verified editor | Accepted |
| [0037](0037-content-delivery-release-boundary-by-function.md) | Content, delivery and release: the aicore boundary is drawn by function | Accepted |
| [0038](0038-skill-descriptor-agent-skills-standard.md) | Skill descriptor: the Agent Skills standard plus digest and provenance | Accepted |
| [0039](0039-eval-result-context.md) | An evaluation result carries the context it was produced in | Accepted |
| [0040](0040-extension-configuration-map-tables.md) | Extension configuration is a map table of the [aicore] section | Accepted |
| [0041](0041-event-envelope-journal-and-delivery.md) | Event envelope, journal-first delivery, cursors and dead letters | Accepted |
| [0042](0042-external-plugin-protocol-and-process-discipline.md) | External plugin protocol 1, describe before use, process discipline and trust | Accepted |
| [0043](0043-validator-profile-and-schema-compatibility.md) | Validator profile with patternProperties and a schema compatibility check | Accepted |
| [0044](0044-instruction-overlays-runtime-resolution.md) | Instruction overlays are resolved at run time | Accepted |
| [0045](0045-telemetry-naming-conventions.md) | Telemetry naming conventions | Accepted |
| [0046](0046-brain-surface-and-vault-lookup.md) | The surface of brain and the vault lookup | Accepted |
| [0047](0047-document-sync-through-a-host-command.md) | Document sync moves to brain and is called through a host command | Accepted |
| [0048](0048-plan-closed-subscriber-and-idempotent-notes.md) | The plan-closed subscriber and idempotent notes | Accepted |
| [0049](0049-module-skills-through-host-provided-buckets.md) | Module skills reach projects through host-provided buckets | Accepted |
| [0050](0050-skiller-settings-in-the-layered-config.md) | Skiller settings live in the layered project config | Accepted |
| [0051](0051-skill-metadata-in-the-index.md) | Skill metadata in the index and `skiller describe` | Accepted |
| [0052](0052-planner-rename-compatibility-alias.md) | `task` becomes `planner` in one rename, with a compatibility plugin for one minor release | Accepted |
| [0053](0053-planner-engine-without-hard-aicore-dependency.md) | The planner engine runs without aicore; aicore is reached through `planner.integration` | Accepted |
| [0054](0054-planner-settings-in-the-layered-config.md) | Planner settings live in the layered `[planner]` configuration | Accepted |
| [0055](0055-planner-events-overlays-and-external-checks.md) | Planner events, command overlays and the `planner:check` extension point | Accepted |
| [0056](0056-execution-scenario-and-one-owner-per-attempt.md) | Execution scenario and one owner per attempt, as minor changes of `plan/v1` | Accepted |
| [0057](0057-orch-on-the-aicore-foundation.md) | `orch` runs on the `aicore` foundation | Accepted |
| [0058](0058-bridges-as-hub-units-and-partner-lookup.md) | Bridges are hub units; partners are found by variable or command, never by path | Accepted |
| [0059](0059-work-source-port-and-evidence-gate.md) | The `orch:work-source` port, owner fencing and the evidence gate | Accepted |
| [0060](0060-execution-protocol-fields-in-exec-v1.md) | Execution protocol fields in `exec/v1`, as minor changes | Accepted |
| [0061](0061-run-policy-packs-engine-choice-and-orch-events.md) | Run-policy packs, engine choice in `[orch]` and `orch.run.*` events | Accepted |
| [0062](0062-engine-conformance-and-non-goals.md) | Engine conformance and the non-goals of `orch` | Accepted |
| [0063](0063-partner-command-links.md) | Modules reach each other through partner commands with JSON output | Accepted |
| [0064](0064-run-analytics-in-analyst-and-event-subscriber.md) | Run analytics live in analyst, and analyst subscribes to ecosystem events | Accepted |
| [0065](0065-maind-configuration-and-state.md) | maind configuration is split into settings and a fleet registry; machine registries move | Accepted |
| [0066](0066-maind-harness-link-and-mcp-projection.md) | maind reaches harness through JSON commands; the MCP projection moves to aicore | Accepted |
| [0067](0067-harness-configuration-and-state.md) | harness hook modes live in the project configuration and a committed carrier | Accepted |
| [0068](0068-instruction-catalog-and-legacy-driver.md) | The instruction catalog holds its targets as data; the legacy run driver finds planner by lookup | Accepted |
| [0069](0069-module-doctor-contract.md) | Module doctors print check-result/v1 and keep probe and repair apart | Accepted |
| [0070](0070-maind-mcp-protocol-negotiation.md) | The maind MCP server negotiates the protocol version | Accepted |
| [0071](0071-core-and-artifex-removal-and-strict-boundaries.md) | core and artifex are removed and the module boundary check is strict | Accepted |
| [0072](0072-umbrella-reads-modules-from-unit-json.md) | The umbrella CLI reads modules from `unit.json`; aliases are data | Accepted |
| [0073](0073-doctor-aggregator.md) | `swissknifeman doctor` aggregates the doctor probes of modules, read-only | Accepted |
| [0074](0074-install-profiles.md) | `swissknifeman install` with profiles; `install.sh` is a wrapper | Accepted |
| [0075](0075-marketplace-from-unit-json.md) | The marketplace and the Codex index are assembled from `unit.json` | Accepted |
| [0076](0076-conformance-kit.md) | Conformance kit for plugins and engines | Accepted |
| [0077](0077-release-bundle.md) | Release bundle: compat manifest, schema package, attestation and checksums | Accepted |
| [0078](0078-installed-form-smoke-and-ci-matrix.md) | Smoke of the installed form and a CI matrix generated from `unit.json` | Accepted |
| [0079](0079-umbrella-front-door-plugin-at-the-root.md) | The `skm` front door is a plugin of the hub root | Accepted |
| [0080](0080-gui-tauri-shell-react-python-control-plane.md) | GUI is a Tauri 2 shell, a React/TypeScript frontend and a Python control plane | Accepted |
| [0081](0081-gui-domains-through-bridges.md) | GUI reaches domains only through bridges `gui-<module>` and the aicore plugin protocol | Accepted |
| [0082](0082-gui-declarative-contributions.md) | GUI contributions are declarative; UI annotations stay outside canonical schemas | Accepted |
| [0083](0083-gui-local-api-security.md) | GUI local API: loopback, session secret, desktop transport adapter | Accepted |
| [0084](0084-gui-state-canonical-files.md) | GUI state: canonical files are the source of truth; SQLite is a rebuildable index | Accepted |
| [0085](0085-portable-workspace.md) | Portable workspace: plans leave the project repository and live in one git root of their own | Accepted |
| [0086](0086-product-philosophy.md) | Product philosophy is a normative document and a pinned root instruction | Accepted |
