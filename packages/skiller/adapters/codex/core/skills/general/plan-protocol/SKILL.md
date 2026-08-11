---
name: plan-protocol
bucket: general
version: 2.25.0
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
`task:plan-audit`, or whenever a `plans/<PLAN-ID>` contract is authoritative. Small single-slice
work may use `task:fix`/`task:dev`; cross-module, compliance, multi-repository, or multi-session
work requires an executable plan.

Rules common to layouts v1 and v2:

- Repository files are the source of truth; chat, memory, MCP output, and generated views are not.
- Read `plan.md` and the selected phase/item carriers before mutation. Follow `Required Reads` in
  declared order and fail closed on a missing required input.
- The authoring-model provenance has three carriers: Meta `Authoring Model`, Update Log role/model,
  and journal `actor`. Missing any carrier is a defect.
- One fact has one owner. Generated carriers are regenerated through their owner and checked.
- External claims use `RAG:✅`; repository-grounded claims use `RAG:—`; unresolved external claims
  use `[UNVERIFIED]`. Ambiguity that blocks readiness is `[NEEDS CLARIFICATION …]`.
- A phase skeleton starts with `> СКЕЛЕТ — не детализирован`; execution requires a detailed item.
- Plans are Markdown SSOT. JSON is a contract, bundle, append-only event stream, or derived view,
  never an alternate handwritten plan.
- Re-opened phase handoff starts with `> УСТАРЕЛ — фаза реопенена`.

## 2. Layout selection and read paths

Layout is selected only by Meta `Layout`:

- **Layout v1:** `Layout` is absent; preserve its monolithic plan/phase/handoff and optional
  evidence carriers.
- **Layout v2:** Meta contains `Layout | v2`. Stable specifications, volatile state, append-only
  history, and generated views are separate carriers. Rules explicitly tagged `[v2]` apply only
  here; `[v1]` rules apply only to v1; untagged rules apply to both.

**Layout v2 carrier contract** — the executor path is exactly:

1. `plan.md` — identity, Context, Execution Rules, Routing.
2. `phases/<Pn>/<Pn>.md` — Phase Context and item index.
3. `phases/<Pn>/<Pn.m>.md` — immutable item specification.
4. `bundles/<Pn.m>.json` — ordered digest-qualified inputs.
5. `phases/<Pn>/<Pn.m>.state.md` — byte-fresh generated state.

The designer additionally reads current decisions/status; the auditor materializes history from
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

Routing correction happens before journal start and never turns the current producer red. A future
carrier is `dependency-not-ready`, not a failure of its producer. Compare inherited red against its
baseline delta. On the first repeated failure fingerprint change tactics; only the next repeat or a
new material risk permits one isolated reviewer. Reuse a prior scoped verdict while scope, SHA, and
risk are unchanged; status, bookkeeping drift, and nits are not review triggers. A deterministic,
non-material plan-bookkeeping defect is repaired inline by its owner, followed by one regeneration
and gate rerun in the same attempt.

Close with two commits: scope implementation, then plan bookkeeping. Append, never rewrite journal
events; `[v2]` regenerates views and runs downstream before handoff. Completion Notes carry exact
evidence; a cancelling/superseding decision adds `**Consequences:**`.

`Closure Protocol | v1` opts into `closure/<Pn>.json`; evidence class is exactly `real`,
`synthetic`, or `baseline_pending`. It records judgement provenance and does not replace the
generated `[v2]` phase-closure view. A terminal phase is a candidate: a fresh GREEN audit precedes
phase close; a RED or unresolved ATTENTION is repaired in its owning item before retrying that gate.

## 5. Routing

Model order is `economy < implementation < frontier`; effort order is `low < medium < high < xhigh`.
Compare both independently: undershoot, ambiguity, or unsupported capability blocks before mutation;
overshoot is recorded. Frozen-spec implementation normally uses implementation/high; frontier is for
open design or irreversible choices. Routing rows are
`| Batch | Items | Model class/effort | Exec | Review | Почему |`; `Exec` is `plan-exec`, `manual`,
or `plan-design`, and default/doubt Review is `full`. A batch inherits its highest review depth.
`plan-exec` requires implementation/medium; `plan-run` executes manual items and prints its actual
class/effort as evidence.

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

Every runnable Next has Model class, Effort, Capabilities, Context, Суть, and Команда; manual has
`Команда: —`. The launch snippet is the copyable form.

For layout v2 the Context field carries EXACTLY one of three values:

- **`continue-root`** — remain in the authoritative root session; default for sequential items.
- **`isolated-child-return`** — bounded child/reviewer returns evidence to the root.
- **`cold-start-root`** — a new root rereads committed carriers.

`[v1]` historical context strings remain readable but are not emitted for layout v2. A v2
`cold-start-root` must give exactly one reason: `context-budget`, `capability-missing`,
`owner-pause-no-resume`, or `whole-plan-independent-audit`. Command names do not select context;
the hard-boundary predicate does. `handoff.Next` always carries the provider-neutral form and the
native launch block together.

## 7. Command protocol, evidence, and safe fallbacks

Commands read repository instructions root→cwd, then the layout-specific read path. They record
session identity, route evidence, journal start/terminal events, exact validation, and commits.
Before mutation and before final close, `task:plan-exec` and `task:plan-close` call
`task_contract.build` and `task_contract.evaluate`. Green closure is the spec's FORM boundary,
not a claim that runtime behavior was exhaustively proved.

Use `task:plan-design` for new/from-draft/phase/item/finish/roadmap; `task:plan-exec` for pinned
implementation items; `task:plan-run` for manual-route items in the current session;
`task:plan-audit` for adversarial design/phase audit; `task:plan-close` for reconciliation,
phase closure, and archive. The command contract defines exact write order and is authoritative
for the operation; this canon defines shared meaning.

Portable execution inputs must be committed or predecessor-produced. Host/chat/tmp/foreign paths
are not committed bundle inputs. An external side effect requires explicit authority. Another
agent's summary is evidence to verify, not self-verification.

Use a factual fallback before stopping: resolve the repository root for wrong cwd/path; paginate or
narrow an oversized read; reconcile a deterministic generated carrier through its owner; and check
PID/output/state before calling a process failed. A missing required carrier, bundle digest mismatch,
unsupported capability, authority boundary, safety concern, or reproduced acceptance failure fails
closed. If the required meaning crosses a package boundary, record the exact gap for its owner and
continue separable in-scope work; do not edit the other package.

## 8. Canon weight and maintenance

`plan-weight.py canon` enforces the measured hard cap, warning fraction, baseline-growth
justification, and expiring exceptions; never raise the cap to fit canon. Recalibrate on tokenizer,
calibration-model, or scoring changes, then regenerate the calibration and run its gates. Delete a
repeated checklist before adding policy: one semantic rule lives in this canon/reference pair and
provider files are additive adapters.

## References

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
