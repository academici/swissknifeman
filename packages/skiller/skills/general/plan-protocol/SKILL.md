---
name: plan-protocol
bucket: general
version: 2.24.0
description: "Executable plans in plans/<ID>: schemas, statuses, routing, semantic Next, and handoff."
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

- **Layout v1:** `Layout` is absent. Preserve the monolithic paths `plan.md`, `phases/Pn.md`,
  `handoff.md`, optional `roadmap.md`, `journal.jsonl`, `brief/`, `findings/`, `research/`,
  `closure/`, `artifacts/`, `workflows/`, `root/`, and `open-questions.md`.
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

`plan.md` sections, in order: `## 0. Meta`, `## 1. Context`, `## 2. Execution Rules`,
`## 3. Routing`, `## 4. Phase Index & Status Board`, `## 5. Decision Log`, `## 6. Update Log`;
`## 7. Contracts` is optional. New v2 plans keep decisions in `decisions/<D-id>.md` and render
the compatible decision view; the compact pointer remains in `plan.md`.

Canonical table literals are `Поле | Значение`, `Items 🟢/всего`,
`D# | Дата | Решение | Почему`, `Дата | Кто (role/model) | Что`,
`Контракт | Версия | Статус | Потребители | Уведомлены`, and
`Контракт | Донор-план | Pinned | Замечено | Реакция`.

Every phase has Phase Context, Phase Status, item specifications, and Phase Handoff. `[v2]` stores
these in separate phase index/item/state carriers; `[v1]` keeps them in `phases/Pn.md`.
Write item fields as `**Field:** value`, in this order:

`Status, Intent, Why, Scope Included, Scope Excluded, Inputs, Files, Required Reads, Implementation Rules, Code Guidance, Validation, Deliverables, Completion Notes, Pending Work, Known Deviations, Escalation Needed`

All 16 fields are mandatory. `—` is the empty value. `Inputs` names predecessor-produced
artifacts; `Required Reads` names files to read before work; `Files` bounds writes. Validation
contains runnable commands and Deliverables names observable outputs. A completed item prints the
two Task Contract verdicts on one line:
`write-site: pre_mutation: <code> · pre_final: <code>`. Both must be `allow`; `n/a` is NOT green.

## 4. Status, readiness, and closure

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
`[NEEDS CLARIFICATION …]` remains. First eligible local validation failure is repaired in the
current root session. The same failure fingerprint repeating, or a risk trigger, permits one
isolated reviewer. Capability/authority boundaries go to the owner.

Close an item with two commits: scope implementation, then plan bookkeeping. Append journal
events; never rewrite history. `[v2]` regenerate state/status/decision/closure/bundle views and
run the downstream gate before handoff. `Completion Notes` carry evidence, exact validation,
commit, remaining work, and known deviations. A decision that cancels or supersedes another adds
`**Consequences:**`.

`Closure Protocol | v1` opts into `closure/<Pn>.json`; evidence class is exactly `real`,
`synthetic`, or `baseline_pending`. It records judgement provenance and does not replace the
generated `[v2]` phase-closure view.

## 5. Routing

Default neutral routing:

| Role | Model class/effort | Work |
|:--|:--|:--|
| issue-planner | frontier/high | design |
| invariant-auditor | frontier/xhigh | audit |
| package-implementer | implementation/medium | implementation |
| small-implementer | economy/low | mechanical low-risk slice |
| repo-explorer | economy/low | read/map |
| docs-curator | implementation/low | documentation/close |

Model order is `economy < implementation < frontier`; effort order is
`low < medium < high < xhigh`. Compare both independently. Exact or overshoot may proceed and is
recorded; undershoot, missing/ambiguous selector, or unsupported capability blocks before mutation.
Effort high+ does not automatically require frontier. Use frontier only for open design decisions
or irreversible contract choices; frozen-spec implementation normally uses implementation/high.

Routing rows use `| Batch | Items | Model class/effort | Exec | Review | Почему |`. `Items` is
exactly one `Pn.m` or one same-phase range. `Exec` is `plan-exec`, `manual`, or `plan-design`.
`Review` is `full`, `light`, or `none`; default/doubt is `full`. Full-review classes include public
contracts, security, fiscal/payment, migration, tenant isolation, and fleet canon. A batch keeps
each item close and inherits the highest review depth.

`task:plan-exec` requires at least implementation/medium. A higher route or effort means
`Exec=manual` unless an explicit safe command contract exists. `task:plan-run` executes manual
items under the current session route and must print the actual class/effort; self-attestation is
evidence, not a machine proof.

## 6. Handoff and semantic Next

`handoff.md` is the rolling owner/design/audit pointer. Title is
`# HANDOFF — <ISO-date> — after <Pn.m|Pn>`. It contains Next, Done, Remaining, Sources of truth,
Open risks, and Workarounds/Deferred/Open questions. The first non-empty Next line declares the
form; prose below cannot change it.

| Форма Next | Когда |
|:--|:--|
| exec-items: task:plan-exec <ID> Pn.m [Pn.k …] | detailed executable item(s) |
| run-items: task:plan-run <ID> Pn.m[-Pn.k] | manual items under current verified route |
| audit-design: task:plan-audit <ID> design | whole-plan pre-exec audit |
| design-phase: task:plan-design <ID> Pn | detail a phase skeleton |
| design-item: task:plan-design <ID> Pn.m | redesign an item |
| design-finish: task:plan-design <ID> finish | reconcile detailed design |
| design-roadmap: task:plan-design <ID> roadmap | refresh execution roadmap |
| audit-phase: task:plan-audit <ID> Pn | audit a terminal phase |
| close: task:plan-close <ID> Pn[.m] | reconcile/close item or phase |
| archive: task:plan-close archive <ID> | archive terminal plan |
| terminal: план закрыт | no protocol work remains |
| manual: <model-class/effort> | no single command; carry bare prompt |
| waiting: <condition> → <target semantic form> | real step not executable yet |

Historical `/task:…`, `ЗАПУСК ВРУЧНУЮ:`, and `ОЖИДАНИЕ:` inputs remain compatible. New handoffs
store the provider-neutral semantic form and separately render Claude `/task:…` or Codex
`$ task:…`. A waiting launch includes `# НЕ раньше:`. Audit findings include, in order,
`РЕЖИМ:`, `ВХОД:`, `СКОУП:`, `НЕ ТРОГАТЬ:`; an audit block declares `Вердикт:`.

Every runnable Next has this launch table:

| Параметр | Значение |
|:--|:--|
| Model class | neutral class |
| Effort | neutral effort |
| Capabilities | required semantic capability ids or `—` |
| Context | one canonical value below |
| Суть | bounded next action |
| Команда | provider invocation or `—` for manual |

For layout v2 the Context field carries EXACTLY one of three values:

- **`continue-root`** — remain in the authoritative root session; default for sequential items.
- **`isolated-child-return`** — bounded child/reviewer returns evidence to the root.
- **`cold-start-root`** — a new root rereads committed carriers.

`[v1]` historical context strings remain readable but are not emitted for layout v2. A v2
`cold-start-root` must give exactly one reason: `context-budget`, `capability-missing`,
`owner-pause-no-resume`, or `whole-plan-independent-audit`. Command names do not select context;
the hard-boundary predicate does. `handoff.Next` always carries the provider-neutral form and the
native launch block together.

## 7. Command protocol and evidence

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

## 8. Canon weight and maintenance

`plan-weight.py canon --budget packages/task/configs/canon-weight-budget.json` enforces D93:
hard cap equals the measured single-read token limit; warning is a declared fraction of the cap;
growth above the declared baseline percentage requires a justification; every exception has an
ISO expiry and follow-up. It prints tokens and physical lines. The vendor guidance of fewer than
500 lines is an independent orientation, not the hard cap. Never raise the read cap to fit canon.

Recalibrate when the tokenizer family changes, the calibration model id changes, or the scoring
asset/classifier changes: rerun the owning calibration probe, regenerate the calibration artifact,
measure this exact carrier, update the budget baseline with a git anchor and justification, run
the canon gate, registry check, task validation, and skiller validation. An expired exception is
ignored and the hard cap applies unconditionally.

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
