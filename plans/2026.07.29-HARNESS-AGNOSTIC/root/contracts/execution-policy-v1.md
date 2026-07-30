---
type: contract
plan: 2026.07.29-HARNESS-AGNOSTIC
contract: execution-policy
status: sealed (P4.2)
exports: "declarative execution policy of the fleet: four sections (spawn_threshold · max_parallel_agents · allowed_agent_roles · delegation_contract), parallelism ceilings as a table by subject and provider, the five mandatory fields of a subagent assignment, the enforcement-point lifecycle (pending/enforced + pending_until), field→consumer tracing, versioning rules and the self-check checklist the P4.3 validator implements"
version: v1
consumers: "P4.3 (data file packages/harness/configs/common/agent-packs/execution-policy.json, validator packages/harness/lib/harness/execpolicy.py, last step of packages/harness/scripts/validate.sh), P4.4 (PLAN grammar of _common.orchestrator in both carriers + pending→enforced transition), P5.1 (release wording of the shipped capability); prose «кап делегирования» in packages/task/commands/{design,research,review,plan-design}.md as a reference consumer (translation to the SSOT is assigned outside this phase); future thin wrapper in roadmap/artifex-thin-wrapper.md"
basis: "plans/2026.07.29-HARNESS-AGNOSTIC/research/08-p4-executor-layer-and-policy.md §3/§4/§5 (carrier measurement, delegation gap, two ceilings); plans/2026.07.29-HARNESS-AGNOSTIC/findings/05-rag-delegation-and-spawn-2026-07-29.md Ф19–Ф22; plans/2026.07.29-HARNESS-AGNOSTIC/findings/04-rag-agent-surface-and-skill-listing-2026-07-29.md Ф17; plans/2026.07.29-HARNESS-AGNOSTIC/findings/03-rag-codex-capability-surfaces-2026-07-29.md Ф11; plans/2026.07.29-HARNESS-AGNOSTIC/research/01-audit-adjudication.md §7 (four sections accepted, two rejected); plans/2026.07.29-HARNESS-AGNOSTIC/root/executor-layer-rescope-v1.md §5 (phase boundary); plan.md D31/D32/D48/D58; form precedent plans/archive/2026.07.18-FOREMAN/root/contracts/artifex-policy-schema.md §2/§5/§7"
verdict: "RAG:✅ 2026-07-29 findings/05 Ф19/Ф20/Ф21/Ф22 (direct WebFetch anthropic.com/engineering/multi-agent-research-system, code.claude.com/docs/en/sub-agents), findings/04 Ф17 (same first-party page — subagent limits), findings/03 Ф11 (learn.chatgpt.com/docs/agent-configuration/subagents — Codex [agents] section) · RAG:— (repo-grounded, tree dde9382a: packages/harness/configs/common/agent-packs/roles.json — catalog_version 1.0.0, roles[0] == (_common, orchestrator) carrying the PLAN grammar and the Parallel-max2 mode; packages/harness/configs/claude-code/agent-packs/_common/agents/orchestrator.md — the second carrier of the same body, 106 lines; packages/harness/configs/common/agent-packs/review-roles.json — extension-table form precedent, 3 940 B; packages/harness/lib/harness/agentpacks.py:930-933 _COMMON_FORBIDDEN, :1108-1124 both provider projections; packages/task/commands/design.md, research.md, review.md, plan-design.md — prose consumers; direct call measured on the same tree: plan_agent_artifact(_common.orchestrator, provider_id='codex') raises HARNESS_ACTIVATION_UNSUPPORTED:codex:command.workflow-carrier:P4 at agentpacks.py:1120, the same limitation already sealed in configs/provider-capabilities.json capabilities[0].support.codex.limitations[1] and root/contracts/codex-parity-verdicts-v1.md §3.12; none of the six canonical marker literals of §5.3 occurs in either carrier today) · [UNVERIFIED] the 1 / 2–4 / >10 scale is a foreign-domain transfer (deep research, not monorepo code work) and the Codex over-ceiling behaviour was never exercised live (D3)"
---

# Contract: execution policy (v1)

**Purpose.** Seal the FORM of the fleet's declarative execution policy: which fields exist, what
they mean, which values they carry with what provenance, who reads each one, where the policy is
enforced, and how the schema may change. The policy answers two questions that today are answered
ad hoc in every session: *when is spawning a subagent justified* and *what a subagent assignment
must contain*.

**Subject — the fleet canon, one for all projects.** The policy is not per-project configuration:
a per-project carrier would split one rule across the onboarded projects on first contact
(`research/08` §3, D31). Per-project execution knobs remain the subject of the frozen donor
contract `plans/archive/2026.07.18-FOREMAN/root/contracts/artifex-policy-schema.md`
(`.artifex/policy.toml`), which this contract does not reopen and does not replace.

**Boundaries (what this policy is NOT).**

- Not code and not data: this file owns rules and form. The data file and the validator are
  produced by `2026.07.29-HARNESS-AGNOSTIC P4.3`, the landing in the orchestrator grammar by
  `2026.07.29-HARNESS-AGNOSTIC P4.4`.
- Not a token budget: no numeric spawn threshold is claimed, because none was measured on our own
  runs (`findings/05`, «Не проверено»). The threshold is an enumerable class of situation.
- Not a second role catalog: `allowed_agent_roles` is a derivation rule over the existing canon.
- Not a runtime supervisor: the driver, run-folder, retry ladder and escalation channels stay out
  of this plan (`root/executor-layer-rescope-v1.md` §5; D38).
- Not a capability-ID producer: the policy introduces no capability identifiers and changes no set
  they are derived from, so `scripts/provider-docs.py --check` is unaffected (D31).

---

## §0. Three artefacts, one meaning

| Artefact | Owner item | Role |
|:--|:--|:--|
| This document (`root/contracts/execution-policy-v1.md`) | P4.2 | schema: fields, types, defaults, normative values, provenance, lifecycle, versioning |
| `packages/harness/configs/common/agent-packs/execution-policy.json` | P4.3 | data: the values of §2–§5, copied from this document verbatim (including every `provenance` string) |
| `packages/harness/lib/harness/execpolicy.py` + last step of `packages/harness/scripts/validate.sh` | P4.3 | gate: the checklist of §10, `--check` non-zero on any violation |

Rule of precedence: **this document is the source of truth for values.** A value in the data file
that differs from §2–§5 is a defect of the data file, not a local decision — the executor either
copies this document or changes it by a D-record in `plan.md` §5.

Home of the data file is `configs/common/agent-packs/` because it is the only directory both
provider projections of roles are rendered from (`agentpacks.py:1108-1124`), and the form
«data + stdlib validator + step in `validate.sh`, without touching the frozen provider contract»
is already paid for by the neighbouring `review-roles.json` (D31).

---

## §1. Top-level form

Closed key set of the data file — exactly these five keys. An unknown top-level key is a
violation, not an ignored extra (a silently tolerated key is how a schema drifts).

| Key | Type | Default | Required | Meaning |
|:--|:--|:--|:--:|:--|
| `policy_version` | str (semver `major.minor`) | — | ✔ | version of THIS schema the file conforms to; v1 of this contract → `"1.0"` |
| `spawn_threshold` | object (§2) | — | ✔ | when spawning a subagent is justified, as an enumerable predicate |
| `max_parallel_agents` | object (§3) | — | ✔ | parallelism ceilings by subject and provider + our own operational cap |
| `allowed_agent_roles` | object (§4) | — | ✔ | derivation rule over the role canon |
| `delegation_contract` | object (§5) | — | ✔ | five mandatory assignment fields + enforcement points |

**Provenance rule (applies to every section).** Any object that carries at least one numeric value
MUST carry a `provenance` string naming the source and, when the number is not ours, saying so.
Foreign numbers are never presented as measured for us: a transferred number carries the literal
`[UNVERIFIED]` inside its `provenance` and `unverified: true` next to it.

---

## §2. `spawn_threshold` — an enumerable class of situation

**Why not a number.** Both first-party sources formulate the indication for spawning through one
predicate — «raw material the parent will not return to» — not through a token count
(`findings/05` Ф20/Ф22). No measurement of «how many tokens of raw material actually stay in the
parent without a spawn» exists on our runs, so a numeric threshold would be an invention.

### 2.1 Fields

| Key | Type | Default | Required | Meaning |
|:--|:--|:--|:--:|:--|
| `decision_rule` | str | — | ✔ | how the two condition lists combine into a verdict |
| `positive_conditions` | array of object | — | ✔ | ALL must hold for a spawn to be justified; ≥1 row |
| `negative_conditions` | array of object | — | ✔ | ANY holding blocks the spawn; MUST contain `parent-reuses-raw-material` |
| `scale_by_task_class` | array of object | — | ✔ | starting fan-out width by task class (foreign-domain numbers) |

Condition row (closed key set): `id` (str, unique across both lists), `text` (str, the condition in
one sentence), `provenance` (str).

`decision_rule` normative value:

> `spawn only if EVERY positive condition holds AND NO negative condition holds; a doubt is a negative`

### 2.2 `positive_conditions` (normative values)

| `id` | `text` | `provenance` |
|:--|:--|:--|
| `bulk-raw-material` | the side task would flood the parent conversation with search results, logs or file contents | `findings/05` Ф22 — first-party `code.claude.com/docs/en/sub-agents` (WebFetch 2026-07-29), quoted verbatim |
| `summary-is-enough` | the parent needs only the condensed result, not the raw material itself | `findings/05` Ф20 — first-party `anthropic.com/engineering/multi-agent-research-system` (WebFetch 2026-07-29): compression is the point, parallelism is the means |
| `separable-objective` | the work has one objective statable in a single sentence with its own boundaries | `findings/05` Ф19 — first-party: an assignment without an objective and boundaries produces duplicated work and gaps |

### 2.3 `negative_conditions` (normative values)

| `id` | `text` | `provenance` |
|:--|:--|:--|
| `parent-reuses-raw-material` | the raw material WILL be needed by the parent on the following steps → do not spawn (mandatory row: this is the condition nothing in the repo records today) | `findings/05` Ф22 — first-party «content you won't reference again»: the negation of the reuse clause is a direct contra-indication |
| `decide-or-integrate` | the task is deciding, integrating or contracting (architecture, ADR, contract verdict) rather than gathering | `findings/05`, cross-check paragraph: «use a subagent for gather/analyze/summarize, keep the main session for decide/integrate/continue» |
| `trivial-single-surface` | one edit in one layer or one file — do it directly | RAG:— repo-grounded: `packages/harness/configs/common/agent-packs/roles.json` `_common.orchestrator` § «Порог делегирования», the rule already canonical in the role body |

### 2.4 `scale_by_task_class` (normative values, foreign domain)

Row (closed key set): `task_class` (str, one of `fact-finding` | `direct-comparison` |
`complex-research`), `agents` (str — a form, not an int, because the source states a range),
`tool_calls_hint` (str), `unverified` (bool), `provenance` (str).

| `task_class` | `agents` | `tool_calls_hint` | `unverified` | `provenance` |
|:--|:--|:--|:--:|:--|
| `fact-finding` | `"1"` | `"3-10 per agent"` | `true` | `findings/05` Ф21 — first-party quote; `[UNVERIFIED]` for us: the numbers come from Anthropic's deep-research domain, not from monorepo code work; starting values, calibration is out of plan scope |
| `direct-comparison` | `"2-4"` | `"10-15 per agent"` | `true` | same source, same `[UNVERIFIED]` reservation |
| `complex-research` | `">10"` | `"clearly divided responsibilities"` | `true` | same source, same `[UNVERIFIED]` reservation; our own ceiling still applies — see `fleet_cap` (§3.3) |

**Interaction rule.** `scale_by_task_class` proposes a WIDTH; `max_parallel_agents` imposes the
CEILING. The ceiling always wins: `complex-research` does not authorise exceeding `fleet_cap` or a
platform ceiling.

---

## §3. `max_parallel_agents` — a table by subject and provider

**Collapsing is forbidden.** Three different subjects carry three different ceilings, and the
framework canon already made exactly this mistake once (`research/07` §1 — a workflow ceiling
written as if it were the session ceiling). `max_parallel_agents` is therefore an object with a
`subjects` array, never a scalar.

### 3.1 Fields

| Key | Type | Default | Required | Meaning |
|:--|:--|:--|:--:|:--|
| `subjects` | array of object | — | ✔ | one row per subject; all three subjects of §3.2 MUST be present, duplicates forbidden |
| `fleet_cap` | object | — | ✔ | OUR operational ceiling, narrower than the platform one (§3.3) |

Subject row (closed key set): `subject` (str, one of `session-agent-tool` | `workflow-runtime` |
`codex-subagents`), `provider` (str, one of `claude-code` | `codex`), `total` (int | null),
`total_scope` (str, one of `session` | `run`), `concurrent` (int | null), `nesting_depth`
(int | null), `settings` (array of str — env vars or config keys), `controlled_by_us` (bool),
`provenance` (str).

`null` means «the platform does not fix this number», not «unknown to us»: absence is recorded, not
guessed (the same discipline `route_evidence.capture_actual` applies to an omitted axis).

### 3.2 Subject rows (normative values)

| `subject` | `provider` | `total` | `total_scope` | `concurrent` | `nesting_depth` | `settings` | `controlled_by_us` |
|:--|:--|:--:|:--|:--:|:--:|:--|:--:|
| `session-agent-tool` | `claude-code` | `200` | `session` | `20` | `3` | `CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION`, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` | `false` |
| `workflow-runtime` | `claude-code` | `1000` | `run` | `16` | `null` | — | `false` |
| `codex-subagents` | `codex` | `null` | `session` | `null` | `null` | `agents.enabled`, `agents.max_concurrent_threads_per_session`, `agents.default_subagent_model`, `agents.default_subagent_reasoning_effort` | `false` |

`provenance` strings (normative, copied verbatim by P4.3):

- `session-agent-tool` — `findings/04` Ф17 · first-party `code.claude.com/docs/en/sub-agents`
  (WebFetch 2026-07-29): 200 per session (v2.1.212+), 20 concurrent (v2.1.217+), nesting depth 3
  (v2.1.219). Platform ceiling, not our measurement; env-tunable by the operator.
- `workflow-runtime` — `findings/04` Ф17 · first-party, same page: agents spawned by a workflow
  script do not count against the session budget; the runtime caps ~16 concurrent
  (`min(16, cores − 2)`, so 16 is an upper bound) and 1 000 per run. Outside our control.
- `codex-subagents` — `findings/03` Ф11 · first-party
  `learn.chatgpt.com/docs/agent-configuration/subagents` (WebFetch 2026-07-29): the ceiling is a
  native `config.toml` `[agents]` key, its value is the operator's, not ours.
  `[UNVERIFIED]` Codex behaviour on exceeding `agents.max_concurrent_threads_per_session` was never
  exercised live (`findings/05`, D3).

**Parity note.** The ceiling section has a native projection on both sides — a Codex key exists —
so this is not a Claude-only rule (`research/08` §5).

### 3.3 `fleet_cap` — our own ceiling

Closed key set: `value` (int ≥ 1), `applies_to` (str — the `subject` it narrows), `condition`
(str), `provenance` (str).

| Key | Normative value |
|:--|:--|
| `value` | `2` |
| `applies_to` | `session-agent-tool` |
| `condition` | `file-independent tasks only; concurrent writers to one working tree are never authorised` |
| `provenance` | RAG:— repo-grounded: `packages/harness/configs/common/agent-packs/roles.json` `_common.orchestrator` § «Режимы исполнения» — the `Parallel-max2` mode is already the canon rule; the policy records the existing fleet ceiling, it does not invent a new one |

`fleet_cap.value` MUST NOT exceed the `concurrent` of the subject it applies to. It narrows exactly
one subject: `workflow-runtime` is a separate subject and is not capped at 2 — a workflow script
fanning out wider than `fleet_cap` is not a policy violation.

---

## §4. `allowed_agent_roles` — a derivation rule, not a list

A second list of role names would diverge from the canon on the first pack change, so the policy
carries the RULE that derives the allowed set.

### 4.1 Fields

| Key | Type | Default | Required | Meaning |
|:--|:--|:--|:--:|:--|
| `source` | str (repo-relative path) | — | ✔ | the role canon the set is derived from |
| `key` | array of str | — | ✔ | the identity of a role inside the canon |
| `rule` | str | — | ✔ | the derivation itself, in one sentence |
| `exclusions` | array of object | `[]` | ✔ | subtractive exceptions; each MUST resolve to a role that exists in `source` |

Exclusion row (closed key set): `pack_id` (str), `role_id` (str), `reason` (str).

### 4.2 Normative values

| Key | Value |
|:--|:--|
| `source` | `packages/harness/configs/common/agent-packs/roles.json` |
| `key` | `["pack_id", "role_id"]` |
| `rule` | `allowed = every (pack_id, role_id) present in the canon for the packs installed in the project, minus exclusions; a role absent from the canon MUST NOT be addressed by a PLAN line` |
| `exclusions` | one row: `{pack_id: "_common", role_id: "orchestrator", reason: "delegate-only role: the orchestrator plans and delegates, it is never a delegation target of its own plan"}` |

**Second-list ban (checkable).** `allowed_agent_roles` MUST NOT carry an array of role names or
role ids under any key other than `exclusions` — the validator rejects keys outside the closed set
above, which is exactly what makes the ban machine-observable rather than advisory.

**Existing consumer.** The PLAN grammar of `_common.orchestrator` already states
«`@<PREFIX>-<role>` — только существующие роли (см. разведку)»; this section is the machine-readable
form of that sentence, and its resolution check is what turns a stale role name into a red gate.

---

## §5. `delegation_contract` — five mandatory assignment fields

### 5.1 The five fields (closed set, order fixed)

Verbatim first-party enumeration (`findings/05` Ф19):
«Each subagent needs an objective, an output format, guidance on the tools and sources to use, and
clear task boundaries.»

| Order | `id` | Meaning of the assignment field | Coverage before this contract (`research/08` §4) |
|:--:|:--|:--|:--|
| 1 | `objective` | one sentence stating what the subagent must achieve | covered — PLAN line `Task N -> @<role> : <goal>` |
| 2 | `output_format` | the shape the result is returned in | **absent** — the single real gap |
| 3 | `tool_guidance` | which tools and skills the work is done with | covered — `skills:` in the PLAN line, `tools:` in the role frontmatter |
| 4 | `source_guidance` | which sources are authoritative and how facts are verified | partial — lived in the role body, not in the assignment |
| 5 | `boundaries` | what the subagent must not touch, and where its work ends | covered — `files:` + `deps:` + the role anti-trigger |

`required_fields` in the data file is an array of exactly these five ids in exactly this order.
Each row (closed key set): `id`, `text`, `provenance`.

### 5.2 Refusal rule

Normative value of `refusal_rule`:

> `an assignment without a declared return format is not issued: the parent would receive arbitrary prose and would have to re-read the raw material, losing the compression the subagent exists for`

Provenance: `findings/05` Ф19 (the named failure mode «Without detailed task descriptions, agents
duplicate work, leave gaps, or fail to find necessary information») and Ф20 (compression as the
purpose of a spawn).

### 5.3 `enforcement_points` — form and canonical markers

The key name `enforcement_points` is fixed HERE because the Validation of both P4.3 and P4.4
references it.

Point row (closed key set):

| Key | Type | Required | Meaning |
|:--|:--|:--:|:--|
| `id` | str | ✔ | stable slug, unique inside the array |
| `carrier` | str (repo-relative path) | ✔ | the file the contract is enforced in; MUST exist |
| `carrier_kind` | str | ✔ | `role-canon-content` \| `markdown-template` |
| `selector` | object | conditional | required iff `carrier_kind == role-canon-content`; forbidden otherwise; closed keys `pack_id`, `role_id`, `field` |
| `field_markers` | object | ✔ | keys are exactly the five ids of §5.1; values are the literal substrings whose presence proves the field landed |
| `grammar_marker` | str | ✔ | the literal substring proving the machine-readable grammar carries the return-format field |
| `status` | str | ✔ | `pending` \| `enforced`; any other value is a violation |
| `pending_until` | str | conditional | required iff `status == pending`, forbidden iff `status == enforced`; form `<PLAN-ID> Pn.m` |

**Canonical marker literals** (fixed by this contract, copied verbatim by P4.3, landed verbatim by
P4.4 — a marker is a contract-level decision precisely so that neither executor can quietly pick an
easier string):

| Assignment field | Marker literal |
|:--|:--|
| `objective` | `- objective:` |
| `output_format` | `- output:` |
| `tool_guidance` | `- tools:` |
| `source_guidance` | `- sources:` |
| `boundaries` | `- boundaries:` |
| grammar field (`grammar_marker`) | `; output:` |

Measured on tree `dde9382a`: none of the six literals occurs in either carrier today, so a marker
check cannot pass vacuously (RAG:— repo-grounded, `python3` substring probe over
`roles.json` `_common.orchestrator.content` and `_common/agents/orchestrator.md`).

**Constraint P4.4 inherits.** The block text landing in the canon must survive the canon's own
prohibitions: provider-specific literals are rejected there and only `{{token:*}}` from the known
set is allowed (`agentpacks.py:935-938`). All six markers above are token-free and provider-neutral
by construction. If a marker still cannot be landed without breaking PLAN parsing, that is an
escalation to this contract (a D-record changing the literal), not a local substitution.

### 5.4 Lifecycle of an enforcement point (D58)

| From → To | Who may do it | Condition |
|:--|:--|:--|
| (declared) → `pending` | the item that declares the point | `pending_until` names the item that creates the carrier content; a `pending` point whose addressee item does not exist in the plan is FORBIDDEN |
| `pending` → `enforced` | only the item named in `pending_until` | the content physically landed in the carrier and the strict check is green on its own; flipping the status to make a Validation green is forbidden |
| `enforced` → `pending` | nobody as an execution decision | weakening is a contract change: a D-record in `plan.md` §5 plus a version bump (§8) |

`status: pending` is a NAMED legal state of the data, not a defect: the validator checks the
address strictly only for `enforced` points, while a `pending` point without `pending_until` is a
violation. That is what keeps «declared but not yet built» distinguishable from «forgotten».

### 5.5 Declared points (normative values)

Both carriers of the same role body must carry the block: the live installer renders from the
template, while the provider-neutral audit and the projection layer read the canon
(`research/08` §4). One carrier is therefore not enough, and each carrier is its own point.

| `id` | `carrier` | `carrier_kind` | `selector` | `status` | `pending_until` |
|:--|:--|:--|:--|:--|:--|
| `plan-grammar-canon` | `packages/harness/configs/common/agent-packs/roles.json` | `role-canon-content` | `{pack_id: "_common", role_id: "orchestrator", field: "content"}` | `pending` | `2026.07.29-HARNESS-AGNOSTIC P4.4` |
| `plan-grammar-template` | `packages/harness/configs/claude-code/agent-packs/_common/agents/orchestrator.md` | `markdown-template` | — | `pending` | `2026.07.29-HARNESS-AGNOSTIC P4.4` |

Both points carry the full canonical `field_markers` map and `grammar_marker` of §5.3 from the
moment they are written (P4.3), because the markers are what P4.4 is obliged to land.

**Codex-side reach — measured boundary, not an assumption.** The orchestrator role declares
`activation_requirements: ["command.workflow-carrier"]`, and the frozen renderer refuses such a
role for Codex: `plan_agent_artifact(role, provider_id="codex", …)` raises
`HARNESS_ACTIVATION_UNSUPPORTED:codex:command.workflow-carrier:P4`
(`agentpacks.py:1120`; measured on tree `dde9382a` by a direct call). This is sealed
knowledge, not a defect of this contract: the P2.1 verdict records the same limitation verbatim in
the capability catalog («a role that requires `command.workflow-carrier` is refused for Codex by
the frozen renderer, so such roles are absent from the Codex projection» —
`configs/provider-capabilities.json` `capabilities[0].support.codex.limitations[1]`,
`root/contracts/codex-parity-verdicts-v1.md` §3.12). Consequence for this contract: the two
declared points are the provider-neutral canon and the Claude-side installation template; a
rendered `.codex/agents/*-orchestrator.toml` does not exist today, so the delegation contract
reaches a Codex host only when that capability gap closes. Claiming a Codex projection of THIS role
as evidence of landing is forbidden by §9.2, and any Validation phrased as «both projections of the
role render» is unsatisfiable for the orchestrator by the frozen contract — a spec matter for
`plan-design`, not something an executor may work around.

**Prose consumers are not enforcement points.** The «кап делегирования» paragraphs in
`packages/task/commands/design.md`, `research.md`, `review.md` and `plan-design.md` restate this
discipline in four different wordings. They are reference consumers, to be pointed at the SSOT
outside this phase; declaring them `pending` is impossible under §5.4, because no item of this plan
creates them.

---

## §6. Sections deliberately NOT introduced

The audit's policy layer proposed six sections; `research/01` §7 accepted four and rejected two,
and this contract keeps that verdict. The two rejected names appear in this repository's policy
vocabulary ONLY here, as rejected:

| Rejected section | Existing carrier of the same fact | Why not duplicated |
|:--|:--|:--|
| `verification_strategy` | the review-gate of the agent pack: `packages/harness/configs/common/agent-packs/review-roles.json` + `packages/harness/lib/harness/reviewroles.py` | a second carrier of one fact is forbidden (`plan-protocol` §3); the pack gate already fixes required sections and verdict gates per role |
| `memory_checkpoint_policy` | the plan journal (`plans/<PLAN-ID>/journal.jsonl`, `packages/task/lib/task/journal.py`) and the sealed run-folder contract of the donor | the checkpoint discipline is already owned, versioned and gated elsewhere |

A fifth section, and the return of either name as a policy FIELD, is a major change (§8) — not an
executor's addition.

---

## §7. Trace: field → consumer (anti «field for the future»)

A field without a named reader does not enter the schema.

| Field | Machine reader | Semantic reader |
|:--|:--|:--|
| `policy_version` | `execpolicy.py` compat check | future wrapper (`roadmap/artifex-thin-wrapper.md`) |
| `spawn_threshold.decision_rule` / `positive_conditions` / `negative_conditions` | `execpolicy.py` (form, mandatory negative row, provenance) | `_common.orchestrator` § «Порог делегирования» in both carriers; the four `packages/task/commands/*.md` prose consumers (translated to the SSOT outside this phase) |
| `spawn_threshold.scale_by_task_class` | `execpolicy.py` (`unverified ⇒ [UNVERIFIED]` in provenance) | the same command prose, which states the discipline today without a number or a task class |
| `max_parallel_agents.subjects` | `execpolicy.py` (three distinct subjects, no scalar) | `_common.orchestrator` § «Режимы исполнения» (`mode:` choice); future wrapper for its own fan-out |
| `max_parallel_agents.fleet_cap` | `execpolicy.py` (`value ≤ concurrent` of `applies_to`) | the existing `Parallel-max2` mode rule of the orchestrator |
| `allowed_agent_roles.*` | `execpolicy.py` (resolution against the canon, exclusions resolve) | the PLAN rule «only existing roles» |
| `delegation_contract.required_fields` / `refusal_rule` | `execpolicy.py` (five ids, order) | the «Контракт задания» block landed by P4.4 in both carriers |
| `delegation_contract.enforcement_points` | `execpolicy.py` (status-driven strictness) | P4.4 as the obliged addressee; P5.1 for release wording |

---

## §8. Versioning

`policy_version` is the semver of THIS schema that the data file conforms to; v1 of this contract
is `"1.0"`. The validator carries the supported major and refuses an unknown one.

| Change | Bump | Examples |
|:--|:--|:--|
| **major** | `2.0` | removing or renaming a required field; narrowing an enum; changing the meaning of `status`; changing a canonical marker literal; changing the five required fields or their order; weakening an `enforced` point back to `pending`; introducing a fifth section or a rejected name from §6 |
| **minor** | `1.1` | a new optional field with a default; a new `subjects` row; a new enforcement point; a new condition row in the predicate; a new `scale_by_task_class` row |
| **patch** | `1.0.1` | wording or `provenance` corrections with no semantic change |

**Forward-compatibility trade-off, stated openly.** Key sets are CLOSED, so an older validator does
not silently tolerate a newer optional field — it reds. This is deliberate: drift detection is worth
more here than tolerance, and the cost is bounded because the data file and the validator live in
the same package and ship in one change. Consequence: a minor bump is never a data-only edit.

**Semantic-drift discipline.** A change of this contract that alters what a field MEANS while
keeping its name is a major bump even if the JSON shape is unchanged — the readers of §7 are prose
and grammar, not only the validator.

---

## §9. What is NOT proof

1. **A green `--check` while a point is `pending` does not prove the delegation contract landed.**
   It proves the declaration is well-formed and has an addressee. Only `enforced` plus a strict
   address check is evidence of landing.
2. **Markers in the canon alone are not proof.** The live installer renders from the template; a
   rule present in only one carrier reaches half the fleet (`research/08` §4). Symmetrically, both
   carriers green is not proof the rule reached a **Codex** host: the orchestrator role has no Codex
   projection by the frozen renderer (§5.5), and no phrasing of a check may pretend otherwise.
3. **Prose in `packages/task/commands/*.md` is not a carrier of this policy.** It is a consumer; as
   long as it restates the rule in its own words, the restatement is a copy, not the SSOT.
4. **The `scale_by_task_class` numbers are not our measurement.** They are a foreign-domain
   transfer (`[UNVERIFIED]`), usable as starting values and nothing more.
5. **The absence of a runtime complaint from Codex is not proof its ceiling was honoured** — the
   over-ceiling behaviour was never exercised (`[UNVERIFIED]`, D3).
6. **The gate covers FORM, not obedience.** Nothing machine-enforces the spawn predicate inside a
   live session: a green `validate.sh` says the policy is well-formed and its enforcement points are
   honestly labelled, never that a session obeyed the predicate. Claiming otherwise would be exactly
   the decorative-gate failure `status` exists to prevent.

---

## §10. Self-check checklist for the P4.3 validator

Every normative MUST of this document appears here with the check that observes it. A condition
that cannot be checked by a command or by the presence of a literal in a named file does not belong
in the schema — it is removed, not softened.

| # | Condition | Checked by |
|:--:|:--|:--|
| 1 | top-level keys are exactly the five of §1 | key-set comparison; unknown or missing key → violation naming the key |
| 2 | `policy_version` present, `major.minor` form, major supported | regex + comparison with the validator's supported major |
| 3 | `spawn_threshold` carries `decision_rule`, non-empty `positive_conditions`, non-empty `negative_conditions`, non-empty `scale_by_task_class` | presence and length checks |
| 4 | `negative_conditions` contains the row `parent-reuses-raw-material` | id lookup |
| 5 | every condition row has `id`/`text`/`provenance`, ids unique across both lists | per-row key check + duplicate scan |
| 6 | every `scale_by_task_class` row with `unverified: true` carries `[UNVERIFIED]` in `provenance`; `task_class` in the closed enum | substring check + enum check |
| 7 | `max_parallel_agents` is an object (never a scalar) carrying `subjects` and `fleet_cap` | type check |
| 8 | all three subjects of §3.2 present exactly once, `provider` in enum, `total_scope` in enum | enum + duplicate scan |
| 9 | `fleet_cap.applies_to` names an existing subject and `fleet_cap.value ≤` that subject's `concurrent` | cross-field comparison |
| 10 | every object carrying a numeric value carries `provenance` | recursive walk over the document |
| 11 | `allowed_agent_roles` keys are exactly the closed set of §4.1 (this is the second-list ban) | key-set comparison |
| 12 | `allowed_agent_roles.source` exists and every `exclusions` row resolves to a real `(pack_id, role_id)` of the canon | `core.safe_load_json` of the canon + key lookup |
| 13 | `delegation_contract.required_fields` is exactly the five ids of §5.1 in that order | list equality |
| 14 | `refusal_rule` is a non-empty string | presence check |
| 15 | every enforcement point has the closed key set of §5.3; `carrier` exists; `carrier_kind` in enum; `selector` present iff `role-canon-content` | per-point structural check |
| 16 | `field_markers` keys are exactly the five ids and the values equal the canonical literals of §5.3; `grammar_marker` equals its canonical literal | string equality against the constants |
| 17 | `status` in `{pending, enforced}`; any other value → violation | enum check |
| 18 | `pending ⇒ pending_until` matching `<PLAN-ID> Pn.m`; `enforced ⇒ pending_until` absent | regex + presence check |
| 19 | `enforced ⇒` all five markers and `grammar_marker` are physically present in the resolved carrier text; `pending ⇒` their absence is NOT a violation | selector resolution + substring checks |
| 20 | `--check` prints every violation in Russian, one per line, naming key and expectation, and exits non-zero on a non-empty list | run of `python3 -m harness.execpolicy --check` plus the negative fixtures of P4.3 |

Negative fixtures P4.3 owes (one class each, from this checklist): unknown key (#1), missing
required field (#3), numeric object without `provenance` (#10), role absent from the canon (#12),
`enforced` point with a non-existent address (#19), `pending` point without `pending_until` (#18).
Positive fixture: the state this contract seals — both points `pending` with
`pending_until: 2026.07.29-HARNESS-AGNOSTIC P4.4`, blocks physically absent, `--check` green.
