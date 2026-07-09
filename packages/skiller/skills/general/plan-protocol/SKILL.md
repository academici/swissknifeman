---
name: plan-protocol
bucket: general
version: 2.0.0
description: "Executable master plans in plans/<ID>: plan/phase/task schemas, 6 statuses, refine loop and DoR gate, canonical plan root, two homes and archive, handoff with launch-block, model routing, /task:plan-* commands."
risk: write
persona: oss-dev
tags: [workflow, planning, handoff, routing, multi-model]
requires: []
produces_for: [session-handoff, complex-task-orchestrator]
outputs: ["plans/<PLAN-ID>/plan.md", "plans/<PLAN-ID>/phases/*.md", "plans/<PLAN-ID>/handoff.md"]
snippets: ["plan-template.md", "phase-template.md", "handoff-template.md", "active-template.md", "launch-block-template.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Plan Protocol

Ecosystem SSOT for the plan protocol: how an executable master plan is structured — a
"strong" model writes it, a "cheap" one executes it without access to the planning chat.
The protocol fixes ONLY Axioma specifics — schemas, gates, markers, pipelines; general
planning practices that plan mode / the model handle on their own are not retold here.

## 1. When to activate

- Multi-phase work longer than one session (the plan outlives context).
- "Strong model plans, cheap model executes" pattern: opus builds the plan,
  sonnet/haiku close items against it.
- Any `/task:plan-*` command invocation (design/exec/close/audit).

**"Do we need a plan?" threshold (heuristic):**

| Task traits | Route |
|:--|:--|
| Small edit, bugfix, single file | `/task:fix` without a master plan |
| Feature in one module, PoC, experiment | `/task:dev` without a master plan |
| Cross-module; compliance (54-FZ/payments/PII); >1 repo; >1 session | `/task:plan-design` with this protocol's gates is MANDATORY |

## 2. Layout

```text
plans/<PLAN-ID>/
├── plan.md            # master plan (Meta, Context, Rules, Routing, Status Board, logs)
├── phases/Pn.md       # one file per phase: phase context, items, phase handoff
├── handoff.md         # rolling "where we are" pointer (overwritten)
├── findings/          # RAG extracts and recon reports (section 16)
├── 20_research/       # the plan's research artifacts
├── artifacts/         # phases' working artifacts, destiny — archive
├── root/              # long-lived material, destiny — project docs (section 3)
└── open-questions.md  # disputed/unresolved (protocol — section 3)
```

Only `plan.md`/`phases/`/`handoff.md` are mandatory — everything else is optional,
per the plan's needs. `PLAN-ID` = `[A-Z][A-Z0-9-]+` (e.g. `AUDIT-W2`, `MIGRATE-V3`).

`plans/` root, next to the plan directories:

- **`plans/ACTIVE.md`** — flat pointer to the active plan. Canon — EXACTLY 4 lines
  (parsed by `plan-lint`): `# ACTIVE`, blank line, `**Active:** <PLAN-ID>` (no active
  plan — `—`), `**Updated:** <YYYY-MM-DD>`. Skeleton — `snippets/active-template.md`.
  Maintained by commands: `plan-design` (new/from-draft modes — sets the new plan's ID)
  and `plan-close` (the WHOLE plan closed — resets to `—`).
- **Draft convention:** any flat `.md` directly in `plans/` (except `ACTIVE.md` and
  `README.md`) is a plan-mode draft; expand it with
  `/task:plan-design from-draft <файл>` (`plan-lint` warns about lingering drafts).

**MD-only rule:** the stored plan format is Markdown with strict markers ONLY. Any JSON
is a derived parser artifact (`plan-lint --json`), never the source of truth.

## 3. Canonical plan root

The semantic difference between the two artifact directories (RAG:✅ P5.1 §2 arc42 —
timeless material at the root, iterations in children):

- **`root/`** — long-lived material whose destiny is project documentation:
  `architecture.md`, `data-model.md`, `contracts/`, `philosophy.md`, `glossary.md`.
  The set is per the plan's needs — not all files are mandatory.
- **`artifacts/`** — phases' working material, archived together with the plan.

**Open Questions protocol** (RAG:✅ P5.1 §7 IETF rough consensus): a disputed point
does NOT block the plan if moved out into `open-questions.md` with one of the statuses:

```text
Exploration
Decision pending (owner needed)
Resolved → D#
```

Rules: a question "hanging" in a phase body without being moved out = audit finding;
closing a plan with pending questions = only `🟠 Done with deviations`; an objection is
recorded substantively ("I don't like it" is not an objection).

**Re-design over closed phases** (RAG:✅ P5.1 §7 superseded chains): a new decision =
a new D# with a "supersedes D#-old" reference; the old D# is NOT edited. Phase reopen:
Status `🟢`→`🟡` + plan Version bump + a D-log entry with the reason.

## 4. plan.md schema

Skeleton — `snippets/plan-template.md`. Sections strictly in this order:

- **`## 0. Meta`** — field table: Plan ID / Title / Version / Status / Document Type /
  Authoring Model / Last Updated / Repository / Related Packages / Execution Mode /
  Target Operator Models / Approval Owner. Optional fields:
  - **Home** — `brain` | `repo:<путь>`: where the plan's executable copy lives (section 12);
  - **Paused By** — which plan seized ACTIVE and when; filled by plan-design mode `new`,
    which appends the field to the previously active plan.
- **`## 1. Context`** — 5–15 lines: what we do and why. Self-contained: the executor
  does NOT see the chat the plan was born in.
- **`## 2. Execution Rules`** — ≤20-line digest of execution rules + plan-specific
  deviations. The full protocol is this skill; do not copy it wholesale.
- **`## 3. Routing`** — ONLY deviations from the SSOT routing matrix (section 9).
  Empty section = defaults apply. Line format:
  `Items | Model/effort AND/OR Tool Capability | Why` — tool-capability
  (typical: `perplexity-web/WebFetch (RAG)`) SUPPLEMENTS model/effort, never replaces it.
- **`## 4. Phase Index & Status Board`** — table `Phase | Title | Items 🟢/total | Status`.
- **`## 5. Decision Log`** — table `D# | Date | Decision | Why`.
- **`## 6. Update Log`** — append-only table `Date | Who (role/model) | What`.
  Hard limit: "What" ≤ 2 lines, canonical format:
  `<item> closed: <1 line of substance> — details in phases/Pn.md <item> Completion Notes`.
  Retelling Completion Notes in the Update Log is FORBIDDEN (EDUFY incident: 54KB plan.md).

## 5. phases/Pn.md schema

Skeleton — `snippets/phase-template.md`. Phase file structure:

- `# Pn — Title`
- **`## Phase Context`** — 5–10 lines, self-contained (the phase is executable
  without reading other phases).
- **`## Phase Status`** — table `ID | Title | Status | Updated`.
- **Items.** Item heading STRICTLY `### Pn.m — Title`. Fields STRICTLY as lines
  `**Field:** value`, in this order:
  `Status, Intent, Why, Scope Included, Scope Excluded, Inputs, Files, Required Reads,
  Implementation Rules, Code Guidance, Validation, Deliverables, Completion Notes,
  Pending Work, Known Deviations, Escalation Needed`.
  Empty value — canonical «—» (not blank, not "N/A").
  Exception: for the `Escalation Needed` field — and ONLY for it — the marker `no`
  is equal in standing to «—».
  **Code Guidance is MANDATORY**: solution style, bans, allowed abstractions, required
  tests, forbidden shortcuts — what a cheap model won't infer on its own.
- **`## Phase Handoff`** — filled when the phase is closed (what was delivered, what's next).

**Skeleton-phase marker.** A phase deliberately left undetailed at authoring time
carries a fixed line in its Phase Context:

```text
> СКЕЛЕТ — не детализирован, разворачивается /task:plan-design <ID> Pn
```

With the marker, empty item fields are legal, including Code Guidance = «—». Without
the marker an empty Code Guidance is a plan defect.

**RAG markers** on load-bearing facts in Intent/Why/Implementation Rules and in the
D-log are mandatory — schema and load-bearing definition in section 7.

## 6. Statuses

EXACTLY 6 canonical strings — copy byte-for-byte (greppable, parser is strict):

```text
⬜ Not started
🟡 In progress
🟢 Done
🟠 Done with deviations
🔴 Blocked
⛔ Skipped by decision
```

Status lives in the plan: finishing work without updating the plan = incomplete
execution. Closed an item → update `Phase Status` and the Status Board in `plan.md`.

**Commit gate on close.** Status `🟢`/`🟠` is NOT set without the item's diff committed:
Conventional Commits (Russian), atomic by meaning (several commits — fine), affected
package's `validate.sh` green BEFORE the commit; review-fix commits are SEPARATE (not
`amend` — traceability: it must show what review caught); no uncommitted diff for the
item's Scope remains in the tree (`git status`); a diff OUTSIDE the item's Scope is not
committed, record it in Pending Work. Incident basis — D12 of plan SKM-AUDIT-004: 4
"closed" items were marked done while their code sat uncommitted in the working tree.

**Phase DoR gate.** A phase is not moved from design to execution until Definition of
Ready passes — checklist and refine loop in section 7. A phase that went to exec with
unresolved `[NEEDS CLARIFICATION]` markers = a plan-audit finding.

## 7. Refine loop and readiness

**Marker `[NEEDS CLARIFICATION: <вопрос>]`** — the canonical way to flag an ambiguity
right in the text of the plan / an item's spec (RAG:✅ P5.1 §1 spec-kit). A disputed
spot at authoring time — either the marker or a question to the owner; an unauthorized
assumption is forbidden. The gate is binary: 0 markers.

**Phase DoR gate** (Definition of Ready, RAG:✅ P5.1 §7 Atlassian) — a fixed checklist;
plan-design must run it before declaring "phase ready", plan-audit checks it
post-factum:

- [ ] All `[NEEDS CLARIFICATION]` resolved (0 markers in the phase).
- [ ] Phase Scope Included / Scope Excluded filled (Goals/Non-Goals equivalent).
- [ ] Alternatives for load-bearing decisions recorded in the D-log.
- [ ] Open Questions distributed across `open-questions.md` statuses (section 3).
- [ ] Load-bearing facts carry RAG markers.

**RAG markers in the schema.** Every load-bearing fact/verdict in an item's
Intent/Why/Implementation Rules and in the D-log carries `RAG:✅ <date/query gist>` or
`[UNVERIFIED]`. Load-bearing = "a project decision stands on this". A load-bearing
point without a marker = schema defect, audit finding.

**Refine loop** — the canonical authoring contour:
design → self-audit (DoR checklist) → edit → repeat until 0 markers.

**Pre-mortem for high-stakes** (fiscal/payments/tenant-isolation/ecosystem core):
before closing a design phase — a round per the Klein protocol (RAG:✅ P5.1 §7,
prospective hindsight +30%): "the plan failed 6–12 months out — why"; independent
recording of causes → clustering → mitigations with an owner in Risks/D-log.

## 8. Handoff standard

`plans/<ID>/handoff.md` — rolling pointer, OVERWRITTEN on every item/phase close
(version history lives in git, not in the file). Skeleton — `snippets/handoff-template.md`.
Fields:

- Heading: `# HANDOFF — <ISO-date> — after Pn.m`
- **Next:** the next command in launch-block form (below).
- **Done:** what is closed.
- **Remaining:** what is left.
- **Sources of truth:** where the truth lives (plan.md, phases/Pn.md, key files).
- **Open risks:** open risks.
- **Workarounds/Deferred/Open questions:** keys match run-report
  `devloop{workarounds,deferred,open_questions}` — cross-checkable with telemetry.

**Launch-block.** Every "what to launch next" output — handoff.Next and the finals of
plan-exec/plan-close/plan-audit reports — must take the fixed form
(`snippets/launch-block-template.md`):

```markdown
| Параметр | Значение |
|:--|:--|
| Model | <модель> |
| Thinking | <effort> |
| Context | <fresh session / continue> |
| Суть | <1 строка> |

````
<голая команда одним code-block, копипаст без правок>
````
```

**Self-sufficiency (cold-start).** The launch-block command must work from a cold
session: plan-ID + input-doc paths (cold-start reads) + an embedded gate approval if
the execution is gated. References like "this session" — only as a supplement.
`plan-lint` checks: handoff.Next contains the launch-block table and a code block (greppable).

Under a master plan the general session handoff (skill `session-handoff`) collapses
here — do not keep a second handoff file.

**"item/phase → handoff → /clear" cycle:** after handoff.md is overwritten, `/clear`
is recommended — the next item starts from reading the plan (plan.md → phases/Pn.md →
handoff.md), not the chat tail. plan-exec and plan-close print the fixed reminder line:
`Context: handoff свежий — рекомендован /clear перед следующим item`.

## 9. Routing & Thinking Policy (SSOT matrix)

Default role→model/effort routing. Plan section `## 3. Routing` stores ONLY
deviations from this table:

| Role | Model/effort | Works in |
|:--|:--|:--|
| issue-planner | opus/high | plan-design |
| invariant-auditor | opus/xhigh | plan-audit |
| package-implementer | sonnet/medium | plan-exec |
| small-implementer | haiku/low ¹ | LOW slices of dev-loop |
| repo-explorer | haiku/low ¹ | repo recon (grep/read/map) |
| docs-curator | sonnet/low | plan-close |

¹ Probe 2026-07-02: a haiku agent with effort=low, launched via the workflow-agent
API, finished successfully (response received) — the runner accepted the
haiku+effort=low pair without error. The probe confirms the parameter is accepted
at the workflow-agent API level; it does NOT verify the behavior of the effort
frontmatter pin inside interactive Claude Code (a different model/effort selection
mechanism) — on mismatch, treat the model's default effort as authoritative.

**Thinking policy:**

- effort **high+ MANDATORY** for: decomposition, conflicting requirements, invariants,
  SemVer-public-API, final verification.
- effort **low MANDATORY** (thinking is harmful — burns tokens for nothing) for:
  grep/read/map, mechanical edits, status updates, docs sync, handoff formatting.

## 10. Escalation (cheap-model protocol)

Triggers — closed enum:

- multi-package refactoring
- unclear architecture
- public contract/SemVer
- protected generated assets
- rule conflict
- unclear acceptance

On trigger the executor leaves THREE greppable artifacts:

1. Blockquote in the item:
   `> 🔴 ESCALATION Pn.m: <причина> | trigger: <из enum> | нужен: plan-design`
2. `**Status:** 🔴 Blocked` on the item.
3. Final report line: `ESCALATION-REQUIRED: Pn.m — <причина>`.

Plan diverged from code → do NOT improvise, escalate: plan-design fixes the plan,
not the executor on the fly.

## 11. Cross-plan patterns

**Cross-plan gate** (precedent AIRESTO ERP-GATE-01): a plan's dependency on another
plan is formalized as a decision doc with a precondition table; every row references
the EXACT Status Board row ID of the donor plan. Reading is one-way: the consumer
reads the donor; the donor does not know about the consumer and is not edited.

**Program plan** (precedents FLEX-IMPL, ECOSYSTEM P4): a coordination plan over
delegates — `Document Type: Program Master Plan (coordination)`; items = milestone
delegates (one delegate plan per item); the item's Validation = a GREEN audit of the
delegate; NO code is written in a program plan. Such a plan's Execution Rules must
forbid `/task:plan-exec` and name the prescribed command for launching delegates.

## 12. Lifecycle: two homes, archive, documentation

**Two-homes model** (RAG:✅ P5.1 §2 docs-as-code: git=SSOT, hub=display/index; no
external canon found specifically for Obsidian↔repo two-way — the mechanism is our
`brain sync`). The plan's SSOT is determined by its stage:

- **before exec starts** — the base plan lives in Brain (canon);
- **at exec start** — the plan moves to the project repo (repo's `plans/<ID>`),
  Meta `Home: repo:<путь>`; the Brain copy becomes a mirror (synced via the
  `brain sync` channel, frontmatter `repo:` — the same mechanism as docs/);
- **during exec** — SSOT = repo; silent edits to the base plan in Brain are
  FORBIDDEN — only via the conflict protocol; default sync direction is repo→Brain
  (mirroring), not the reverse;
- **after completion** — sync back → archive → migrate root/ into docs.

**Conflict protocol.** The base plan changed during execution → the executor does NOT
merge silently: records a `temporary divergence` in the current item's Known
Deviations → escalation per section 10; the owner decides — accept into the working
copy as a new D# or defer to the end of the phase.

**Skills — same principle:** the skills' SSOT is always swissknifeman; vendor copies
in projects are updated only by `skiller vendor/connect`; a local edit of a vendor
copy = defect, the path is a contribution to the SSOT
(see `package-contribution-protocol`).

**Plan→archive→docs pipeline** (RAG:✅ P5.1 §2 Diátaxis + Oxide "committed =
implemented"). On plan terminality — command `/task:plan-close archive <ID>`:

1. The plan moves to `plans/archive/<ID>` as a SEPARATE commit
   `chore(plan): archive <ID>`.
2. Project documentation is assembled from `root/` by Diátaxis types:
   architecture/philosophy → explanation; data-model/contracts → reference;
   phase guides → how-to.
3. A migration checklist (what moved to docs, what stayed in the archive) — in the
   final handoff.

## 13. Command protocol

| Command | Model/effort | Does |
|:--|:--|:--|
| `/task:plan-design` | opus/high | new plan / new phase / item specs; refine loop + DoR gate |
| `/task:plan-exec` | sonnet/medium | execute an item; self-closing (updates statuses + handoff) |
| `/task:plan-close` | sonnet/low | status reconciliation / phase close / `archive` mode |
| `/task:plan-audit` | opus/xhigh | adversarial phase audit; verdict GREEN/ATTENTION/RED |

## 14. Plan-quality checklist

- [ ] Every item executable by sonnet with no context beyond the plan.
- [ ] Required Reads finite and ordered (not "look around the repo").
- [ ] Code Guidance filled for every item (not «—»).
- [ ] An undetailed phase carries the skeleton marker — not "just empty fields".
- [ ] Load-bearing facts/verdicts carry `RAG:✅`/`[UNVERIFIED]` markers.
- [ ] Open Questions don't "hang" in phase bodies — moved to `open-questions.md` with a status.
- [ ] handoff.Next contains a launch-block (table + code block).
- [ ] Phase-first: phases close sequentially, items don't jump between phases.
- [ ] `plan-lint` green.

## 15. Per-project deployment

Plans live IN THE PROJECT, not in `~/.claude/plans/`: top-level key
`plansDirectory: "plans"` in the project's `.claude/settings.json` (shared, committed).
Rollout — three layers:

- `harness hooks --target <проект> --plans-dir plans` — targeted knob (a key already
  set to a different value is respected — not overwritten);
- `maind sync --only plans-dir,plans-doc` — fleet of onboarded projects
  (opt-out: `project.plans_dir="off"`);
- `skiller integrate` — new onboardings (plans-dir block, default "yes").

The convention is delivered to the project by the managed CLAUDE.md block
`maind:plan-conventions` (provisioner `plans-doc`). Bridge from built-in plan mode: the
approved plan is saved as a flat draft in `plans/` → `/task:plan-design from-draft <файл>`
expands it into `plans/<ID>/` per this skill's templates (draft deleted, history in git).

## 16. Plan artifacts: findings/

`plans/<PLAN-ID>/findings/<Pn>-<slug>.md` — the standard home for plan artifacts: RAG
extracts and recon reports, so future plan work doesn't repay the cost of reconstructing
"where did this come from" (RAG/subagent extracts are cheap artifacts for future iterations).

- **Path and name:** `plans/<PLAN-ID>/findings/<Pn>-<slug>.md` (`Pn` — phase, `slug` —
  kebab topic); example — `plans/SKM-AUDIT-004/findings/`.
- **What goes there:** a RAG extract (source URL + verification date + verdict), a
  subagent recon report, a diagnosis/repro — **compact synthesis, not raw material**.
- **How items reference it:** an item whose work relies on the artifact lists the file in
  its `Inputs`/`Required Reads` — the downstream executor reads the file instead of
  reconstructing context from chat.
- **Optional:** `findings/` isn't mandatory for every plan/item — required only when the
  item declares the file in its `Deliverables`. The item's 16-field schema is unchanged;
  `plan_lint.py` does not check this directory (not its layer).

## 17. Related skills

- `task-brief-template` (general) — single task without a master plan.
- `session-handoff` (general) — arbitrary-session handoff; under a master plan the
  handoff lives in `plans/<ID>/handoff.md`.
- `complex-task-orchestrator` (general) — decomposition and context routing.
- `context-economy` (general) — Plan→Clear→Execute, token discipline.
- `anti-drift` (general) — executor iteration discipline, circuit breaker.
- `package-contribution-protocol` (architect) — contribution to the SSOT instead of
  editing vendor copies (section 12).

<!-- ru-source-sha256: 8a6962e58e0ae8b7bde1f0bece8b16fb6f5d57e67b7691ef11c7cd45ef7628aa -->
