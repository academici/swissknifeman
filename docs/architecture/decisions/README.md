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
