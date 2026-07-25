# Provider command routing contract

**Version:** v1.0.0

**Status:** frozen

**Approval Owner:** Dmitry Vostrikov

**Approval:** D84, 2026-07-21 (delegated under D79)

**Basis:** D4, D19, D24–D27, D38/D44, D79; frozen provider capability,
configuration, artifact, migration-gates and skill-publication contracts v1.0.0

## Identity

The stable identity of a task command is `task:<command-name>`. The name is the basename of
one canonical `packages/task/commands/<command-name>.md` source. It is lowercase kebab-case,
provider-neutral and MUST NOT be derived from a UI prefix, rendered path, model selector,
plugin-cache path or display label. Published identities are not renamed or reused.

`/task:<command-name>` and `$ task:<command-name>` are provider invocation projections of the
same identity. They are not aliases or separate commands. The initial semantic alias set is
empty for every current command. Unknown, duplicate or ambiguous identity fails before work.

## Command inventory

This is the complete canonical inventory at the v1.0.0 freeze. Each source occurs exactly
once. `routing-required` means that the invoked plan item's minimum is authoritative.

| Command ID | Kind | Canonical source | Arguments | Semantic output | Routing mode | Minimum class | Minimum effort | Aliases |
|:--|:--|:--|:--|:--|:--|:--|:--|:--|
| `task:design` | intent | `packages/task/commands/design.md` | design brief | durable design/decision artifacts, no implementation code | fixed | `frontier` | `high` | `[]` |
| `task:dev` | intent | `packages/task/commands/dev.md` | brief, slices or durable plan reference | implementation, tests and risk-adaptive review | fixed | `implementation` | `high` | `[]` |
| `task:fix` | intent | `packages/task/commands/fix.md` | narrow defect/edit | minimal patch and focused verification | fixed | `implementation` | `medium` | `[]` |
| `task:make-workflow` | workflow-authoring | `packages/task/commands/make-workflow.md` | workflow type and purpose | plan-owned workflow projection plus static review verdict | fixed | `implementation` | `high` | `[]` |
| `task:research` | intent | `packages/task/commands/research.md` | research question | verified synthesis with provenance | fixed | `frontier` | `high` | `[]` |
| `task:review` | intent | `packages/task/commands/review.md` | code/doc artifact reference | read-only adversarial findings | fixed | `frontier` | `xhigh` | `[]` |
| `task:plan-design` | plan-protocol | `packages/task/commands/plan-design.md` | plan ID and design mode | plan/design carriers and next-step handoff | fixed | `frontier` | `high` | `[]` |
| `task:plan-exec` | plan-protocol | `packages/task/commands/plan-exec.md` | plan ID and item list | implementation, validation, closed item and handoff | fixed | `implementation` | `medium` | `[]` |
| `task:plan-run` | plan-protocol | `packages/task/commands/plan-run.md` | plan ID and manual item list | the `plan-exec` lifecycle under the session route | inherited-plan | `routing-required` | `routing-required` | `[]` |
| `task:plan-close` | plan-protocol | `packages/task/commands/plan-close.md` | plan ID plus item, phase or archive mode | reconciled/closed/archived plan state | fixed | `implementation` | `low` | `[]` |
| `task:plan-audit` | plan-protocol | `packages/task/commands/plan-audit.md` | plan ID plus phase or design mode | append-only independent audit verdict | fixed | `frontier` | `xhigh` | `[]` |

A conforming catalog reader derives its expected set directly from the canonical directory,
rejects non-Markdown/service files, and compares exact IDs and source paths to this table.
Missing, extra or duplicate members are `CMD_CATALOG_MISMATCH`; a renderer's output is never
allowed to define the expected set.

## Semantic schema

Every immutable command record contains exactly these semantic fields:

| Field | Contract |
|:--|:--|
| `contract_version` | Supported command-routing contract SemVer. |
| `command_id` | Stable identity from the inventory. |
| `kind` | `intent`, `workflow-authoring` or `plan-protocol`. |
| `source` | Canonical source identity, project-relative POSIX path and exact `sha256:` content digest. |
| `aliases` | Ordered semantic aliases; empty in this freeze. |
| `argument_contract` | Provider-neutral input meaning and required plan identifiers/modes. |
| `output_contract` | Observable semantic result; wrapper prose is not part of it. |
| `routing` | `fixed` minimum or `inherited-plan`, with independent class and effort. |
| `capability_requirements` | Ordered stable requirements and accepted support levels. |
| `plan_semantics` | Referenced statuses/fields/Next/orchestration rules, or empty. |
| `projections` | Provider-keyed mapping/version/provenance references, never provider data in the semantic fields above. |

Descriptions and provider frontmatter are projection metadata. Canonical workflow bodies
remain in `packages/task/commands`; a cache/vendor copy is a locked Rendered Artifact, not a
new source. Unknown field or unknown contract major fails before render or invocation.

## Model classes

The closed ordered class axis is:

```text
economy < implementation < frontier
```

The class expresses the minimum semantic capability/cost tier, not a provider model name.
Provider selectors such as `haiku`, `opus` or `gpt-*` MUST NOT appear in semantic records.
A provider projection maps each class once. Class comparison uses this order only; marketing
names, price and release date do not affect comparison.

## Effort

The closed ordered effort axis is independent of model class:

```text
low < medium < high < xhigh
```

An invocation satisfies routing only when both observed axes meet or exceed their minima.
Raising effort does not raise model class and raising model class does not satisfy a missing
effort minimum. `task:plan-run` inherits both minima from the selected item and then applies
the same comparison to the actual session route.

## Capabilities

Command requirements use stable lowercase dotted IDs and the capability contract support
levels `native`, `adapted`, `unsupported`. The v1 requirement vocabulary is:

| Requirement | Observable promise |
|:--|:--|
| `skills.repository` | Load the provider-native task adapter from the repository/plugin projection. |
| `command.filesystem-read` | Read declared repository/plan inputs. |
| `command.filesystem-write` | Write only the declared task/item targets. |
| `command.git-read` | Inspect repository history/diffs. |
| `command.git-write` | Create only task-authorized commits. |
| `command.external-research` | Use an explicitly available research/RAG surface. |
| `command.subagents` | Run declared subagent/reviewer stages. |
| `command.workflow-carrier` | Resolve the provider projection of a semantic orchestration carrier. |

Each command catalog record declares the smallest set required by its body/mode. Optional
stages stay optional only where the canonical body supplies a sequential fallback. A required
capability with missing/unknown/unsupported support returns `CMD_CAPABILITY_UNSUPPORTED` before
work. Provider-native extensions remain explicit; one provider's success cannot mask another
selected provider's failure.

## Provider mappings

Mapping envelope fields are `provider_id`, `mapping_version`, `class_selectors`,
`effort_selectors`, `capability_bindings`, `invocation_binding`, and ordered `evidence` records
(`source`, `verified_at`, `scope`, `claim`). The initial mapping version is `1.0.0`.

| Provider ID | `economy` | `implementation` | `frontier` | Effort mapping | Provenance |
|:--|:--|:--|:--|:--|:--|
| `claude-code` | `haiku` | `sonnet` | `opus` | native `low`, `medium`, `high`, `xhigh` | current task frontmatter and plan-protocol §9 on this frozen tree; capability evidence verified 2026-07-19 |
| `codex` | `gpt-5.6-luna` | `gpt-5.6-terra` | `gpt-5.6-sol` | native `low`, `medium`, `high`, `xhigh` | D38/D44 and `findings/P7-openai-model-routing-2026-07-19.md`; model evidence verified 2026-07-19 |

The Codex `economy` selector is mapped but no current command has that fixed minimum. Mapping
does not imply account availability. Availability is checked at invocation; missing selector,
unsupported effort or more than one candidate for a class is fail-closed. A selector/evidence
change is a mapping version change and updates downstream provenance.

## Invocation

The invocation renderer receives explicit provider ID, validated command record, arguments,
mapping and capabilities. It does not read cwd/home/global registries to choose a provider.

| Provider | Native template | Identity rule | Provenance |
|:--|:--|:--|:--|
| `claude-code` | `/task:<command-name> <arguments>` | `/` and plugin namespace are UI/provider syntax | current committed slash commands/plugin surface |
| `codex` | `$ task:<command-name> <arguments>` | `$ ` is a UI prefix and the space after `$` is mandatory | owner-observed D19, `brief/01-refinements.md` |

Arguments are appended without changing semantic plan IDs, cold-start reads, gate approvals or
scope payload. Display labels and aliases cannot select a command. A malformed provider prefix,
missing mandatory Codex space, unknown command or provider-disabled projection is rejected.

## Routing gates

Routing is evaluated before status mutation, filesystem write, subprocess, external call or
subagent launch:

1. resolve exact semantic identity and enabled provider;
2. validate contract/mapping versions and required capabilities;
3. resolve a unique provider selector and effort;
4. compare observed class and effort independently to the minimum;
5. render provider invocation only after all previous gates pass.

Exact routes are legal. Overshoot on either axis is legal and reported as
`CMD_ROUTE_OVERSHOOT`; it never rewrites the semantic minimum. Any undershoot is
`CMD_ROUTE_UNDERSHOOT` and blocks work. Unknown, unavailable or ambiguous selectors never
fall back to an arbitrary available model. `task:plan-exec` keeps its fixed
`implementation/medium` pin; `task:plan-run` compares the session route against the plan item.

## Plan semantics

Provider adapters preserve these semantic literals byte-for-byte:

- statuses: `⬜ Not started`, `🟡 In progress`, `🟢 Done`, `🟠 Done with deviations`,
  `🔴 Blocked`, `⛔ Skipped by decision`;
- item fields in order: Status, Intent, Why, Scope Included, Scope Excluded, Inputs, Files,
  Required Reads, Implementation Rules, Code Guidance, Validation, Deliverables,
  Completion Notes, Pending Work, Known Deviations, Escalation Needed;
- commit topology, journal lifecycle, phase-first gates and audit verdict literals.

`Next` stores a semantic carrier, not a rendered slash/UI command. Its closed kinds are
`exec-items`, `run-items`, `audit-design`, `design-phase`, `design-item`, `audit-phase`,
`close`, `archive`, `terminal`, `manual`, and `waiting`. A carrier includes command ID or
terminal kind, plan/item IDs, arguments, context kind and optional cold-start scope payload.
Claude and Codex render the same carrier through `Invocation`; historical provider strings
remain compatibility inputs and are not blanket-rewritten.

An orchestration carrier is semantic data with `kind`, `orchestration_id`, ordered input
references, required capabilities and provider-projection reference. A Claude projection MAY
bind it to `Workflow({scriptPath: ...})`; a Codex projection MAY bind it to a generated task
skill using native subagents. `scriptPath` and tool spelling are projection data, never the
semantic identity. Missing `command.subagents`/`command.workflow-carrier` support blocks with
`CMD_CAPABILITY_UNSUPPORTED`; it is not silently converted to a single-agent run.

## Diagnostics

Every diagnostic has this structured envelope:

```json
{
  "severity": "error|warning|info",
  "code": "CMD_STABLE_CODE",
  "provider_id": "codex",
  "command_id": "task:plan-exec",
  "path": "/routing/model_class",
  "required": {},
  "observed": {},
  "provenance": [],
  "message": "human-readable text",
  "next_action": "operator-safe remediation"
}
```

`code`, `provider_id`, `command_id`, `path`, `required`, `observed`, `provenance` and
`next_action` are stable/machine-readable; message may be localized. Error codes are:

| Code | Condition and outcome |
|:--|:--|
| `CMD_ID_UNKNOWN` | No canonical identity; refuse before work. |
| `CMD_ID_AMBIGUOUS` | More than one identity/alias candidate; refuse. |
| `CMD_CATALOG_MISMATCH` | Missing/extra/duplicate source or projection; refuse before render. |
| `CMD_VERSION_UNSUPPORTED` | Unknown contract/mapping major or unsupported minor; no fallback. |
| `CMD_PROVIDER_DISABLED` | Effective provider is not selected; no projection/work. |
| `CMD_CAPABILITY_UNSUPPORTED` | Required capability is missing/unknown/unsupported; no work/write. |
| `CMD_MAPPING_MISSING` | No selector/effort binding; no fallback. |
| `CMD_MAPPING_AMBIGUOUS` | Multiple selector candidates/provenance conflict; refuse. |
| `CMD_ROUTE_UNDERSHOOT` | Either observed axis is below minimum; stop before status mutation. |
| `CMD_ROUTE_OVERSHOOT` | Legal route above minimum; report without changing the minimum. |
| `CMD_INVOCATION_INVALID` | Provider prefix/arguments/carrier cannot be rendered exactly; refuse. |
| `CMD_SOURCE_DRIFT` | Source digest differs from catalog/lock; check/repair required, no adoption. |

Errors return no invocation. Diagnostics from two providers remain provider-qualified and
aggregate non-green when either selected required projection fails.

## Compatibility

Legacy configuration without provider selection preserves only the current Claude command
surface and bytes; it does not generate or invoke Codex implicitly. Current task IDs,
frontmatter pins, bodies, plugin registration, six statuses, item fields and journal/commit
semantics remain compatibility gates.

Contract major changes identity, axes/order, routing outcome, plan literals, diagnostic meaning
or invocation identity. Minor adds a command/capability/projection without changing existing
results. Patch is editorial/evidence-only. Mapping versions change independently: selector or
effort changes are minor when minimum semantics remain satisfied, major when an existing class
can no longer be represented compatibly. Unknown major fails closed. Historical plans are
read through a compatibility projection; bulk provider-name rewriting is forbidden.

## Golden examples

| Case | Semantic input | Claude projection | Codex projection or diagnostic |
|:--|:--|:--|:--|
| G1 fixed intent | `task:fix`, `implementation/medium`, argument `repair parser` | `/task:fix repair parser`, `sonnet/medium` | `$ task:fix repair parser`, `gpt-5.6-terra/medium` |
| G2 frontier audit | `task:plan-audit`, `frontier/xhigh`, argument `PLAN P4` | `/task:plan-audit PLAN P4`, `opus/xhigh` | `$ task:plan-audit PLAN P4`, `gpt-5.6-sol/xhigh` |
| G3 inherited plan | `task:plan-run`, item minimum `implementation/high`, matching session | `/task:plan-run PLAN P4.2`, observed `sonnet/high` | `$ task:plan-run PLAN P4.2`, observed `gpt-5.6-terra/high` |
| G4 legal overshoot | `task:fix`, minimum `implementation/medium`, observed frontier/high | invocation plus `CMD_ROUTE_OVERSHOOT` | invocation plus `CMD_ROUTE_OVERSHOOT` |
| G5 undershoot | `task:plan-audit`, observed implementation/xhigh | `CMD_ROUTE_UNDERSHOOT`, no status/write | `CMD_ROUTE_UNDERSHOOT`, no status/write |
| G6 missing mapping | `task:design`, provider mapping lacks frontier | `CMD_MAPPING_MISSING`, no invocation | `CMD_MAPPING_MISSING`, no invocation |
| G7 cold-start Next | carrier `audit-phase`, plan/item inputs and scope payload | `/task:plan-audit PLAN P4` with identical payload | `$ task:plan-audit PLAN P4` with identical payload |
| G8 orchestration | semantic carrier requires subagents/provider binding | `Workflow({scriptPath: ...})` only from verified Claude binding | generated skill/native-subagent binding, otherwise `CMD_CAPABILITY_UNSUPPORTED` |
| G9 malformed Codex UI | `task:fix` with provider prefix `$task:` | not applicable to Claude binding | `CMD_INVOCATION_INVALID`; required form is `$ task:fix` |

Each golden asserts semantic input first, then both projections or a structured diagnostic.
Expected cases are authored from this contract and MUST NOT be regenerated from renderer output.

## Approval

D84 freezes this contract as v1.0.0 through the D79 delegated owner approval. The approval is
substantive and atomic:

- **C1 — identity/inventory:** stable `task:*` identities and the complete exact canonical set;
- **C2 — semantic schema:** one command source/catalog with provider data only in projections;
- **C3 — routing axes:** ordered neutral classes and independent effort with two-axis gates;
- **C4 — mappings/invocation:** versioned evidence-backed Claude/Codex selectors and native syntax;
- **C5 — plan/capability safety:** preserved literals, semantic Next/orchestration carriers and
  fail-closed capability/mapping/undershoot behavior;
- **C6 — compatibility/evidence:** legacy Claude-only behavior, structured diagnostics,
  normative goldens and unchanged authority boundaries.

Exact delegated approval record:

```text
APPROVE P4.1 COMMAND-ROUTING C1-C6 AS WRITTEN UNDER D79
```

This approval opens only P4.2–P4.5 against the frozen contract. It authorizes no package code
inside P4.1, live/user-global install, provider-config/permission change, FOREMAN/fleet write or
P5+ execution.
