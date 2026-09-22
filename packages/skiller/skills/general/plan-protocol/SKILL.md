---
name: plan-protocol
bucket: general
version: 2.36.0
description: "Executable plans in plans/<ID>: strict contracts, adaptive execution, and semantic handoff."
when_to_use: "Use when designing, executing, closing, or auditing an executable master plan."
risk: write
persona: oss-dev
tags: [workflow, planning, handoff, routing, multi-model]
requires: []
produces_for: [session-handoff, complex-task-orchestrator]
outputs: ["plans/<PLAN-ID>/plan.md", "plans/<PLAN-ID>/phases/", "plans/<PLAN-ID>/handoff.md"]
snippets: ["plan-template.md", "phase-template.md", "handoff-template.md", "active-template.md", "launch-block-template.md", "roadmap-template.md", "code-guidance-patterns.md", "journal-template.md", "index-template.md", "closure-template.md", "decision-record-template.md", "item-state-template.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Plan Protocol

Canon version: `plan-protocol-v2`. This is the compact entry carrier for executable plans.
It owns identity, invariants, closed enums, routing, and navigation. Detailed carrier schemas
and layout-dependent procedures live in [references/plan-layout-v2.md](references/plan-layout-v2.md);
the snippets are copies, not independent rules.

## 1. When to activate and invariants

Activate for `task:plan-design`, `task:plan-exec`, `task:plan-run`, `task:plan-close`,
`task:plan-audit` when the owner explicitly selects plan work or an exact cited local workflow
policy requires it. Follow the Task package's shared intent-routing canon; ordinary work may proceed
directly from a message or task file. Create a plan only when requested; preserve an explicitly
selected plan and a separately requested design/review boundary.

Rules common to layouts v1 and v2:

- New plans use `YYYY.MM.DD-№N-CODENAME` with a positive ordinal unique within that date;
  Meta `Title` starts with `План №N — …`. Historical plan IDs remain readable and are never renamed.
- New persisted work has a stable repository-local `Short ID` (`PLAN1` plan, `TASK1` task).
  Outside its directory, qualify local references (`PLAN1.D35`, `PLAN1.P2.3`); legacy work uses
  `<PLAN-ID> <local-ID>`. Read [work references](references/work-references.md) when assigning
  IDs or citing work, including in code or generated text.
- Repository files are the source of truth; chat, memory, MCP output, and generated views are not.
- Read `plan.md` and the selected phase/item carriers before mutation. Follow `Required Reads` in
  declared order and fail closed on a missing required input.
- The authoring-model provenance has three carriers: Meta `Authoring Model`, Update Log role/model,
  and journal `actor`. Missing any carrier is a defect.
- One fact has one owner. Generated carriers are regenerated through their owner and checked.
- `plan-lint` verifies the generated bundle of the next runnable v2 item before it can dispatch;
  generate that carrier with `plan-views.py bundle --item Pn.m`. Future predecessor-dependent
  bundles remain deferred until their producer commits its declared artifact.
- External claims use `RAG:✅`; repository-grounded claims use `RAG:—`; unresolved external claims
  use `[UNVERIFIED]`. Ambiguity that blocks readiness is `[NEEDS CLARIFICATION …]`.
- A phase skeleton starts with `> СКЕЛЕТ — не детализирован`; execution requires a detailed item.
- Plans are Markdown SSOT. JSON is a contract, bundle, append-only event stream, or derived view,
  never an alternate handwritten plan. A sealed journal may be rewritten only by an accepted
  Owner-D# `journal-migration/v1` whose complete preimage, per-line operations, source/target
  digests and receipt remain in `journal-migrations/`; ordinary repair stays append-only.
- Re-opened phase handoff starts with `> УСТАРЕЛ — фаза реопенена`.

## 2. Layout selection and read paths

`Layout | v2` is the only executable layout. Missing or `v1` declarations fail closed with
`PLAN_LAYOUT_V1_RETIRED`; read their inert source archive or use the prior compatible tag.
For root-wide lint, archived dated v2 plans before `2026.09.09` are likewise inert: later
state, downstream and handoff rules must not require rewriting their historical evidence.
Linting a named archive explicitly remains available for forensic verification.
Stable specifications, volatile state, append-only history, and generated views are separate carriers.

**Layout v2 carrier contract** — the executor path is exactly:

1. `plan.md` — identity, Context, Execution Rules, Routing.
2. `phases/<Pn>/<Pn>.md` — Phase Context and item index.
3. `phases/<Pn>/<Pn.m>.md` — immutable item specification.
4. `bundles/<Pn.m>.json` — ordered digest-qualified inputs.
5. `phases/<Pn>/<Pn.m>.state.md` — byte-fresh generated state.

The executor first calls `task.plan_recovery.prepare()` to validate the selected item and converge
its deterministic state/bundle, then exposes only the returned `task.plan_context` snapshot. It may
paginate only immutable snapshot bytes by cursor; each member needs a matching
digest and terminal marker, while a gap, transport truncation, or changed live source fails before
journal mutation with `PLAN_CONTEXT_TRUNCATED`/`PLAN_CONTEXT_DIGEST_MISMATCH`. The designer additionally reads current decisions/status; the auditor materializes history from
`journal.jsonl`; the owner reads status, gates, and handoff. `[v2]` `handoff.md` is not on the
executor path. `[v2]` phase closure has two distinct carriers: optional judgement evidence in
`closure/<Pn>.json`, and generated contract/result view `phases/<Pn>/<Pn>.closed.md`. Neither
replaces the other. Full carrier/reader tables and failure codes are in the reference.

## 3. Plan and phase contracts

`plan.md` owns Meta, Context, Execution Rules, Routing, Status Board, Decision Log, and Update Log;
Contracts are optional. Every item has the 16 ordered fields named by `plan-layout-v2.md`; `—` is
empty. Inputs are predecessor evidence, Required Reads precede work, Files bound writes, and
Validation/Deliverables are observable. Closure prints exactly
`write-site: pre_mutation: <code> · pre_final: <code>`; both codes must be `allow`.
Optional `Authority` declares `routine` or one finite `[OWNER-GATE:GATE-ID]` with exact branch/scope.
Read the authority/calendar contract in the layout reference for protected execution or timed waits.

## 4. Status, readiness, and adaptive execution

There are EXACTLY 6 canonical strings:

```text
⬜ Not started
🟡 In progress
🟢 Done
🟠 Done with deviations
🔴 Blocked
⛔ Skipped by decision
```

Terminal statuses are 🟢, 🟠, 🔴, and ⛔. Use 🟢 only when every acceptance condition is green
and scope stayed within the contract. Use 🟠 for material delivered deviations. Use 🔴 only at a
genuine authority/capability boundary, not for an ordinary repairable failure. `⛔` requires an
explicit owner decision. When a stopped item can resume, record `Возобновление:` with the exact
condition.

Before execution: the item has concrete intent/scope/inputs/files/validation/deliverables, all
dependencies are terminal, required reads resolve, routing is unambiguous, and no
`[NEEDS CLARIFICATION …]` remains. This initial contract is strict; inside it the owning root
may group ready adjacent work, choose the local order, and repair a reversible in-scope defect.

Use this loop for every failure signal; a tool exit, status label, audit finding, or dirty tree is
not itself a product verdict:

| Evidence-first loop | Action in the owning root | Terminal only after reproduction |
|:--|:--|:--|
| observe → minimal reproduce → classify → act → verify | retain the smallest useful evidence and verify the resulting scope/acceptance delta | acceptance, safety, authority |
| procedural / transient / dependency-not-ready / unrelated-pre-existing | use the safe fallback, local repair, bounded wait, or continue independent work | no |
| unknown non-idempotent write | reconcile actual state before retry or close | safety until reconciled |
| external process result | reconcile PID, output, and state before terminalizing | acceptance/safety only |

Journal results `routing-rejected`, `decision-pending`, `local-repair`, and `block-candidate` are
durable observations: they do not change item status or consume an execution attempt. Before any
block, checkpoint stop, or redesign, write a closed `repair-decision/v1`: exact red original
carrier, baseline/candidate delta, affected-path ownership, bounded diff, material-surface matrix,
and pre/post validation. `task.plan_repair.evaluate()` alone returns
`repair-in-current-attempt`, `gather-evidence`, `block-candidate`, or `design-required`. A clean
red baseline without a proved candidate delta, or a bounded reversible all-nonmaterial repair,
continues in the owning attempt even for an attributed path outside `Files`; rerun the exact
original carrier. `design-required` needs a decision question, evidence gap, alternatives, and
expected decision artifact for a new unapproved outcome/contract choice. Product, dependency and
test edits or a file-count threshold alone do not require design. Public/security impact needs
evidence and appropriate verification; ungranted authority remains a gate. A material block candidate uses `block-candidate/v1` bound to the repair
digest; every external candidate has verified RAG evidence, and one fresh non-executor reviewer in
`isolated-child-return` returns evidence under `block-confirmation-rubric-v1`. The block reducer
consumes that upstream repair result without reclassification. Only `JUSTIFIED` may become a
terminal block; `AVOIDABLE`, `INSUFFICIENT_EVIDENCE`, `OUT_OF_SCOPE`, and `MALFORMED` continue
repair/evidence without opening a new design pass.
Every block capsule declares `scope_coverage` and concrete `boundary_evidence`. Broad failure size,
file count, elapsed time, or a large diagnostic set never proves a boundary. An in-scope acceptance
failure always decomposes and continues local repair in the same attempt; `JUSTIFIED` without a
concrete authority, capability, safety, or declared-scope boundary is reduced to evidence gathering.

For a declared ``producer-readiness/v1`` edge, terminal evidence carries exactly one typed
readiness record. Nonempty output binds a positive deterministic candidate set; empty output is
valid only by one accepted owner `D#`. Bundle/downstream expose its digest-bound projection, and a
valid projection is a green downstream carrier. Use `task.plan_readiness.correction_decision()` as
the only continuation reducer: verified/no-op continues, missing/stale repairs in the same attempt,
a proved contract conflict plus `phase-reentry-justification/v1` may reopen a terminal phase, and
`fix-branch/v1` may target only a declared priority item. The decision is nonterminal and is visible
in status/returns. Lint and delivery reject terminal-phase `plan-design` without exact re-entry
evidence. Terminal close also rejects every qualified repair whose exact original carrier was not
rerun green in a later immutable record.

Phase audit is read-only over product. `audit-attention` or `audit-red` can finish the reviewer
with `decision.action=return-owning-continuation`, reproduced evidence IDs, `scope_class=<owning item>`, `recovered=false`,
`terminal=false`, and an exact `exec-items:`/`run-items:` owning item of the same phase.
The phase remains open; journal, lint and delivery consume the same policy. Without an admitted
audit, GREEN alone admits close. Missing or RED acceptance evidence is owning repair, not audit admission. After executor
repair, verify the changed risk delta and retain unaffected evidence.
Historical RED authority/block outcomes with `waiting:`/`terminal:` remain readable.
The audit budget limits redundant independent audits, not authorized reversible repair.
Repeated failure without new information requires a changed tactic or checkpoint.

A phase audit is admitted only by one accepted, unsuperseded `audit-admission/v2` decision. Its
bounded residual-risk question, target phase and material candidate fingerprint, audit run,
owner-message provenance, and canonical scope digest must match the requested run. The in-progress
journal event reserves that consent; a terminal event consumes it. Foreign, stale, ambiguous,
agent-authored, or consumed consent is invalid, and every repeat needs a new material hypothesis and
fresh consent. Without admission, material risk produces at most a bounded recommendation and never
an `audit-phase` Next.

Routing correction happens before journal start and never turns the current producer red. A future
carrier is `dependency-not-ready`, not a failure of its producer. Compare inherited red against its
baseline delta. On the first repeated failure fingerprint change tactics; only the next repeat or a
new material risk permits one isolated reviewer. Reuse a prior scoped verdict while scope, SHA, and
risk are unchanged; status, bookkeeping drift, and nits are not review triggers. A deterministic,
non-material plan-bookkeeping defect is repaired inline by its owner, followed by one regeneration
and gate rerun in the same attempt.

Close with one scoped commit containing implementation and affected bookkeeping by default.
A second commit requires a real ownership/session boundary or digest-input collision. Append, never rewrite journal
events; `[v2]` regenerates views and runs downstream before handoff. An executable item terminal
event carries reducer-owned `terminal-evidence/v1`, bound to the current item-spec digest and every
declared Validation carrier. A GREEN receipt is current while relevant product/test/tool/config
inputs and environment are unchanged; review, close, and delivery reuse it. A relevant change reruns
the affected delta, and a live gate reruns at its live boundary. Closure/bookkeeping-only change
regenerates its carrier once and runs its structural check without invalidating independent product
evidence. Any red carrier keeps the item in progress. Explicit acceptance, security, and release
gates remain binding; change an excessive frozen carrier transparently through the existing contract
rules, never by silent omission. `closed-deviations` is not an escape hatch: it still requires green
Validation plus a closed `recoverable-validation-gap/v1` record proving why a
material/outside-scope/unsafe residual cannot be repaired in this attempt.
`blocked`/`escalated` requires an authority or block reducer terminal action. Completion Notes carry
exact evidence; a cancelling/superseding decision adds `## Consequences`.
Use the decision-record template's YAML metadata and literal `Решение` / `Почему` headings;
terminal preparation rejects invalid decision records before appending the journal event.
Before journal/product mutation, derive `evidence-graph/v1` from the committed item spec, bundle,
decisions, producer-readiness and declared Files. A real `Files ∩ digest_inputs` collision with a
fresh closure requirement is `SELF_INVALIDATING_EVIDENCE_ANCHOR`: split spec→product→closure;
otherwise collapse the anchors. Registry-owned volatile journal/view/handoff carriers are
bookkeeping unless the item explicitly declares their product semantics in Deliverables. Closure
proves declared product bytes identical to the product anchor; empty or missing-only anchors fail
with `PRODUCT_COVERAGE_MISSING`. Use backticks around each Files path and keep explanatory prose
outside them. Unnumbered Required Reads may use semicolons outside quoted paths/annotations.
Before `audit-green`, regenerate
audit-owned projections once, rebuild the candidate and persist `audit-finalization/v1` with the
exact `phase_close_gate` admission; `plan-close` consumes that admission rather than discovering a
new audit cycle.
Before product work, `validation-admission/v1` checks deterministic local command prerequisites.
A definitely absent literal Make target creates a nonterminal repair-inline observation in the same
attempt; dynamic Make definitions remain unknown rather than manufacturing a missing-target block.

`Closure Protocol | v1` opts into `closure/<Pn>.json`; evidence class is exactly `real`,
`synthetic`, or `baseline_pending`. It records judgement provenance and does not replace the
generated `[v2]` phase-closure view. A ready-to-close phase is a candidate. Execution/handoff and
standalone close call
`task.plan_assurance.evaluate()` (through the compatibility facade
`task.plan_gates.phase_audit_policy`) over the same runtime-built candidate snapshot. Every new
phase declares one handwritten `Phase Assurance | v1` block: Impact, Integration Seams, Live or
Irreversible, Audit Intent, and Rationale. `Routing.Review` and item count are item-execution
depth, never phase-audit admission. Missing legacy assurance is an advisory migration finding.
<!-- i18n-keep: Audit Intent: light -->
Historical `Audit Intent: light` normalizes to `legacy-light`; `required` and `auto` retain their
enum values. All three remain readable but advisory: none admits audit or rewrites historical
events. A phase with current
GREEN item evidence and satisfied acceptance/safety gates direct-closes by default, including
multi-item and integration phases. RED or missing evidence returns its owning repair. Material risk
without matching `audit-admission/v2` produces a bounded recommendation while GREEN still
direct-closes. After an admitted GREEN audit, `audit-impact/v1` classifies the mismatch for
bookkeeping rebind, affected validation repair, evidence gathering, or owner review. `delta`/`full`
describe impact only and never authorize another audit; every new audit requires a fresh residual-risk
question and candidate/run-bound owner consent. RED or unresolved ATTENTION is repaired in its owning item.
A terminal blocked item remains fail-closed, except for an explicit accepted, non-superseded
phase-scoped owner D#: its `item` is `Pn`, `items` is exactly `Pn` plus every `Pn.*`, and it
carries `` `phase-close: terminal-blocked-deviations` ``. That D# permits only a
`closed-deviations` phase close and `🟠 Done with deviations` phase projection; it never
rewrites the RED/blocked item history, audit evidence, or release authorization.

## 5. Routing

Model order is `economy < implementation < frontier`; effort order is `low < medium < high < xhigh`.
Compare both independently: undershoot, ambiguity, or unsupported capability blocks before mutation;
overshoot is recorded. Frozen-spec implementation normally uses implementation/high; frontier is for
open design or irreversible choices. Routing rows are
`| Batch | Items | Model class/effort | Exec | Review | Почему |`; `Exec` is `plan-exec`, `manual` (also accepted as `plan-run`),
or `plan-design`. Choose Review from concrete item risk: ordinary low-risk work uses self-check and
affected tests, bounded integration adds the necessary package/integration check, and independent
review requires a named hard risk or explicit owner requirement. Uncertainty gathers evidence rather
than defaulting to full. A batch inherits its highest justified review depth.
`task_contract.resolve_exec` owns execution-mode normalization for both compiler and lint.
`plan-run` resolves to the existing `manual` mode: it shares the canonical `plan-exec` lifecycle,
keeps the raw command in `declared_exec` and routing digests, and preserves the attested owner route.
Unknown spellings fail closed; alias resolution never substitutes pinned model/effort or authority.

`plan-exec` requires implementation/medium; `plan-run` executes manual items and prints its actual
class/effort as evidence.

`plan-run` resolves the installed canonical command through `task.command_catalog`, then captures
the current route only through provider-neutral `task.route_evidence.capture_launch()`. Codex argv
and Claude Code session JSONL are additive adapters over one normalized record; missing or ambiguous
evidence is `ROUTE-UNVERIFIABLE`, not an undershoot and never a product block. The start journal event
binds this record to a `route-run-receipt/v1`; pre-final reloads that receipt, recaptures the current
provider route, and rejects a changed, stale, or cross-session run.

For every new layout-v2 plan, `Batch` and `Review` are mandatory and Routing covers every item.
`Batch=solo` means one independently launched item and its `Почему` must name the concrete boundary
that makes reuse uneconomic or unsafe. Otherwise group adjacent items of one phase when they share
a producer/consumer chain, files, required reads, setup, or validation context and one session saves
more rereading/setup than it adds coupling. Do not split merely because items have separate commits,
deliverables, or per-item close gates: those gates still run inside the batch. A batch never crosses
a phase audit/close boundary, mixes `Exec` modes, hides an owner/irreversible gate, or exceeds the
remaining context budget. Its launch route and review are the maxima of its rows and capabilities are
the union. New ordinary groups start their `Почему` with `recommended:`: grouping is a recommendation,
and a ready subset or dependency-safe order is admitted with current input/readiness checks.
Keep checkpoints in the existing journal. Explicit atomic/mandatory groups use `required:`;
historical unmarked groups and their receipts keep exact membership/order or bound suffix
semantics. Changing a frozen mandatory group requires its existing decision carrier.
Ambiguous and stale requests stay non-mutating (`BATCH_REQUIRED`, `BATCH_AMBIGUOUS`, `BATCH_STALE`).

Workflow requirement is a line-scoped positive declaration in Phase Context, not a keyword grep:
`scriptPath` or a positive orchestration/multi-agent statement requires a canonical workflow asset.
An explicit negation in that same statement does not; it never suppresses a separate positive line.
Authoring and audit use this one predicate rather than copying a regex into command prose.

## 6. Handoff and semantic Next

`handoff.md` is the rolling owner/design/audit pointer. Title is
`# HANDOFF — <ISO-date> — after <Pn.m|Pn>`. It contains Next, Done, Remaining, Sources of truth,
Open risks, and Workarounds/Deferred/Open questions. The first non-empty Next line declares the
form; prose below cannot change it.

Semantic Next is one of `exec-items`, `run-items`, `audit-design`, `design-phase`, `design-item`,
`design-finish`, `design-roadmap`, `audit-phase`, `close`, `archive`, `terminal`, `manual`, or
`waiting`; its command is the corresponding `task:plan-*` form. Manual carries a bare prompt;
waiting carries its executable condition and target form.

Historical `/task:…`, `ЗАПУСК ВРУЧНУЮ:`, and `ОЖИДАНИЕ:` inputs remain compatible. New handoffs
store the provider-neutral semantic form and separately render Claude `/task:…` or Codex
`$ task:…`. A waiting launch includes `# НЕ раньше:`. Audit findings include, in order,
`РЕЖИМ:`, `ВХОД:`, `СКОУП:`, `НЕ ТРОГАТЬ:`; an audit block declares `Вердикт:`.

A GREEN item closes inside its `plan-exec`/`plan-run` invocation: persist terminal evidence and
journal, regenerate changed views, and, when it is the final item of a directly closable phase,
create the phase closure before deriving Next. Evaluate `phase_audit_policy` once over the rebuilt
candidate. Matching consent may produce `next_kind=audit-phase`; the default GREEN result closes the
phase in place. Handoff is computed from post-closure state and dependencies and never launches
`plan-close` for the current result or repeats `plan-exec`/`plan-run` for the current item. The
`close` form remains compatible for an explicitly requested standalone reconciliation.

Completion of one item or an admitted batch is not terminality of the whole plan. An unfinished
phase forbids `Context: terminal` and a terminal Next; `none` is not a declared Next form.
Preserve the actual successor even when it is outside the completed batch. Do not execute outside
the admitted scope; at a real owner-requested new-session boundary, persist the successor's Routing
and render its native command. Never replace that handoff with only a completion summary.

After a GREEN item, materialize the actual successor and obey its typed Context before responding.
`continue-root` means begin a compatible ready successor inside the owner-authorized admitted scope
in the same root. Continue that scope without asking between ordinary items. When the owner asked
only for the completed scope, persist lifecycle `scope-complete` and a post-close checkpoint. Its
`continue-root` decision uses reason `authorized-scope-complete`: stop product writes and report the
exact successor as a recommendation for this chat. Chat completion does not terminate the plan,
expand authority, or imply a new process. If no ready successor exists, name the missing scope or
decision; if the entire goal is complete, say so without inventing more mandatory work.
An explicit request for a new session updates lifecycle to `owner-requested-new-session`, captures a
fresh checkpoint and renders the post-close successor. A previous `continue-root` does not override
that request. Separate design/review requests remain within their requested artifact boundary.

At a fresh-session executable handoff, provide a metadata table with Batch, Model class, Effort,
Capabilities, Context, and Суть; the table never carries the invocation. Immediately after it,
render exactly one copyable provider-native command block for the active provider adapter. Claude
Code emits its native slash form; Codex emits a `bash` block that launches `codex` with pinned cwd,
model, effort, approval, and sandbox. Never infer the provider from an example and never print both
native providers. For `waiting`, preserve the exact gate before the block with `# НЕ раньше:`.
Manual carries a fenced bare prompt instead. Legacy table rows named `Команда` remain readable for
old plans but are never emitted. Non-execution Next uses `Batch: n/a`.

For layout v2 the Context field carries EXACTLY one of three values:

- **`continue-root`** — remain in the authoritative root session; default for sequential items.
- **`isolated-child-return`** — bounded child/reviewer returns evidence to the root.
- **`cold-start-root`** — a new root rereads committed carriers.

`[v1]` historical context strings remain readable but are not emitted for layout v2. A v2
`cold-start-root` must give exactly one reason: `context-budget`, `capability-missing`,
`owner-pause-no-resume`, `owner-requested-new-session`, `whole-plan-independent-audit`, or
`design-root-terminal`. Command names
do not select context; the hard-boundary predicate does. `handoff.Next` always carries the
provider-neutral form; a fresh-session handoff also carries the native launch block.

Before any runnable Context is written, build one `task.plan_continuity.WorkEstimate` from the
provider-attested route/capabilities, context health, digest-bound remaining batch, loaded-input
reuse, cold-start cost, lifecycle, and durable checkpoint, then call `task.plan_continuity.reduce`.
Persist that decision's `context`; pass the same typed decision to `PlanNextCarrier`. Renderers,
delivery receipts, and plan-lint validate this result and never choose continuity independently.
Unavailable context telemetry defaults to `continue-root`; `waiting-owner` suppresses a runnable
successor; `waiting-external` persists its observation checkpoint and exact time/predicate continuation;
DecisionRequest recovery preserves `resume-root` whenever that root still exists. A command, phase,
directory, ordinary test failure, generated drift, or a design-looking file name is never a context
boundary by itself.

Before a terminal response, `plan-exec`, `plan-run`, and `plan-close` build a
`terminal-delivery-receipt/v1` from the terminal journal pointer/run ID, current state/closure,
and exact persisted handoff recommendation. A nonterminal or stale carrier returns
`FINAL_BEFORE_TERMINAL_FORBIDDEN` and keeps the dispatch active. Design/audit delivery builds the
non-product `handoff-recommendation-receipt/v1`. Every final response labels
`Рекомендация следующего шага:` and copies the receipt's exact recommendation; a bare item ID
is not a delivery receipt. Build it only after same-invocation item/eligible-phase closure, so its
recommendation cannot point back to that closure or current item. Use the shared renderer via
`plan-delivery.py --kind terminal --render-final` (with plan directory and subject, or a verified
receipt) whether or not an optional terminal-admission lease is installed. That lease governs
transport admission; it does not create the obligation to report Next.

**AUDIT CONTINUATION.** A completed `task:plan-audit` invocation does not itself select a new
root. Build and persist the same `plan_continuity.WorkEstimate` used for every runnable successor;
the reducer selects `continue-root`, `isolated-child-return`, or a supported cold-start reason
from route, capability, context, owner-pause, and independence evidence. The audit root may
continue when that evidence permits it; independent review and route evidence remain mandatory.

**DESIGN-ROOT-TERMINAL.** A completed `task:plan-design` invocation is an authoring boundary:
its root must not execute or spawn the successor, even when the successor is compatible, ready,
or the original brief also mentions later implementation. A design launch block is a routed
recommendation, never execution authority. Every runnable successor has
`cold-start-root: design-root-terminal` and a native fresh routed root launch block that pins the
successor's model and effort. Execution begins only in a separate routed invocation after the
design result has been returned to the owner.

## 7. Command protocol, evidence, and safe fallbacks

Commands read repository instructions root→cwd, then the layout-specific read path. They record
session identity, route evidence, journal start/terminal events, exact validation, and commits.
Before mutation and before final close, `task:plan-exec` and `task:plan-close` call
`task_contract.build` and `task_contract.evaluate`. Green closure is the spec's FORM boundary,
not a claim that runtime behavior was exhaustively proved.

Before recommending `task:plan-design` for an existing phase, inspect its actual item carriers and
generated state. A phase whose items are already detailed and whose first unfinished item is ready
for execution receives `task:plan-exec`, not another design pass. `task:plan-design` is for
new/from-draft scope or a concrete new contract decision; a file count, a failed ordinary check, or
the phrase “next/new phase” is not a design trigger. Use `task:plan-exec` for pinned
implementation items; `task:plan-run` for manual-route items in the current session;
`task:plan-audit` for a design audit or an explicitly admitted adversarial phase audit;
`task:plan-close` for explicitly
requested standalone reconciliation or archive. Item execution owns its GREEN item close and an
eligible final-item phase close. Mechanical data dependencies determine write order; commands recommend a working approach.
Independent safe actions may be reordered within Scope, dependencies and Acceptance.

Portable execution inputs must be committed or predecessor-produced. Host/chat/tmp/foreign paths
are not committed bundle inputs. An external side effect requires explicit authority. Another
agent's summary is evidence to verify, not self-verification.

Use a factual fallback before stopping: resolve the repository root for wrong cwd/path; paginate or
narrow an oversized read; reconcile a deterministic generated carrier through its owner; and check
PID/output/state before calling a process failed. A missing required carrier, bundle digest mismatch,
unsupported capability, authority boundary, safety concern, or reproduced acceptance failure fails
closed. If the required meaning crosses a package boundary, record the exact gap for its owner and
continue separable in-scope work. Explicitly authorized cross-package work reads each package
guide and may proceed in the current session.

## 8. Canon weight and maintenance

`plan-weight.py canon` enforces the measured hard cap, warning fraction, baseline-growth
justification, and expiring exceptions; never raise the cap to fit canon. Recalibrate on tokenizer,
calibration-model, or scoring changes, then regenerate the calibration and run its gates. Delete a
repeated checklist before adding policy: one semantic rule lives in this canon/reference pair and
provider files are additive adapters.

## References

- Mandatory layers selected by Task commands: [common principles](references/common-principles.md),
  [design](references/design-mode.md), [execution](references/execution-mode.md), and
  [review](references/review-mode.md). The full canon remains on demand for exact schema details.
- Layout/carrier/read-path/state/closure details:
  [references/plan-layout-v2.md](references/plan-layout-v2.md).
- Source-evidence verification and portability rules are summarized in sections 1 and 7; a plan
  may pin stricter project-local contracts through its ordered bundle.
- Copyable forms: [snippets/](snippets/).
- Project-facing explanation: `packages/task/docs/` and aggregate `docs/task/`.

## Canon literals

<!-- i18n-keep: Closure Protocol -->
<!-- i18n-keep: Поле | Значение -->
<!-- i18n-keep: Items 🟢/всего -->
<!-- i18n-keep: D# | Дата | Решение | Почему -->
<!-- i18n-keep: Дата | Кто (role/model) | Что -->
<!-- i18n-keep: Контракт | Версия | Статус | Потребители | Уведомлены -->
<!-- i18n-keep: Контракт | Донор-план | Pinned | Замечено | Реакция -->
<!-- i18n-keep: Команда -->
<!-- i18n-keep: > СКЕЛЕТ — не детализирован -->
<!-- i18n-keep: ЗАПУСК ВРУЧНУЮ -->
<!-- i18n-keep: [NEEDS CLARIFICATION -->
<!-- i18n-keep: RAG:✅ -->
<!-- i18n-keep: RAG:— -->
<!-- i18n-keep: [UNVERIFIED] -->
<!-- i18n-keep: план закрыт -->
<!-- i18n-keep: > УСТАРЕЛ — фаза реопенена -->
<!-- i18n-keep: ОЖИДАНИЕ: -->
<!-- i18n-keep: Вердикт: -->
<!-- i18n-keep: РЕЖИМ: -->
<!-- i18n-keep: ВХОД: -->
<!-- i18n-keep: СКОУП: -->
<!-- i18n-keep: НЕ ТРОГАТЬ: -->
<!-- i18n-keep: pre_mutation: -->
<!-- i18n-keep: pre_final: -->
<!-- i18n-keep: write-site: -->
<!-- i18n-keep: **Consequences:** -->
<!-- i18n-keep: Возобновление: -->
