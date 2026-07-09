---
name: plan-protocol
bucket: general
version: 0.2.0
description: "Executable master plans in plans/<ID>: plan/phase/task schemas, 6 statuses, handoff standard, model routing, /task:plan-* commands."
risk: write
persona: oss-dev
tags: [workflow, planning, handoff, routing, multi-model]
requires: []
produces_for: [session-handoff, complex-task-orchestrator]
outputs: ["plans/<PLAN-ID>/plan.md", "plans/<PLAN-ID>/phases/*.md", "plans/<PLAN-ID>/handoff.md"]
snippets: ["plan-template.md", "phase-template.md", "handoff-template.md", "active-template.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Plan Protocol

Ecosystem SSOT for executable master plans: a strong model writes the plan, a cheap
model executes it without access to the planning chat.

## 1. When to activate

- Multi-phase work longer than one session (plan outlives context).
- "Strong model plans, cheap model executes": opus builds the plan, sonnet/haiku close items.
- Any `/task:plan-*` command (design/exec/close/audit).

## 2. Layout

```text
plans/<PLAN-ID>/
├── plan.md          # master plan (Meta, Context, Rules, Routing, Status Board, logs)
├── phases/Pn.md     # one file per phase: phase context, items, phase handoff
└── handoff.md       # rolling "where we are" pointer (overwritten)
```

`PLAN-ID` = `[A-Z][A-Z0-9-]+` (e.g. `AUDIT-W2`, `MIGRATE-V3`).

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

## 3. plan.md schema

Skeleton — `snippets/plan-template.md`. Sections strictly in this order:

- **`## 0. Meta`** — field table: Plan ID / Title / Version / Status / Document Type /
  Authoring Model / Last Updated / Repository / Related Packages / Execution Mode /
  Target Operator Models / Approval Owner.
- **`## 1. Context`** — 5–15 lines, self-contained: the executor never sees the chat the plan was born in.
- **`## 2. Execution Rules`** — ≤20-line digest + plan-specific deviations; full protocol is this skill, do not copy it wholesale.
- **`## 3. Routing`** — ONLY deviations from the SSOT matrix (section 7). Empty = defaults apply.
- **`## 4. Phase Index & Status Board`** — table `Phase | Title | Items 🟢/total | Status`.
- **`## 5. Decision Log`** — table `D# | Date | Decision | Why`.
- **`## 6. Update Log`** — append-only table `Date | Who (role/model) | What`.

## 4. phases/Pn.md schema

Skeleton — `snippets/phase-template.md`. Phase file structure:

- `# Pn — Title`
- **`## Phase Context`** — 5–10 lines, self-contained (phase executable without reading other phases).
- **`## Phase Status`** — table `ID | Title | Status | Updated`.
- **Items.** Item heading STRICTLY `### Pn.m — Title`. Fields STRICTLY as lines
  `**Field:** value`, in this order:
  `Status, Intent, Why, Scope Included, Scope Excluded, Inputs, Files, Required Reads,
  Implementation Rules, Code Guidance, Validation, Deliverables, Completion Notes,
  Pending Work, Known Deviations, Escalation Needed`.
  Empty value — canonical «—» (not blank, not "N/A").
  **Code Guidance is MANDATORY**: solution style, bans, allowed abstractions, required
  tests, forbidden shortcuts — what a cheap model won't infer on its own.
- **`## Phase Handoff`** — filled when the phase is closed.

## 5. Statuses

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
item's Scope remains in the tree (`git status`); a diff OUTSIDE Scope is not committed,
record it in Pending Work. Incident basis — D12 of plan SKM-AUDIT-004: 4 "closed" items
were marked done while their code sat uncommitted in the working tree.

## 6. Handoff standard

`plans/<ID>/handoff.md` — rolling pointer, OVERWRITTEN on every item/phase close
(history lives in git, not in the file). Skeleton — `snippets/handoff-template.md`. Fields:

- Heading: `# HANDOFF — <ISO-date> — after Pn.m`
- **Next:** `/task:plan-exec <ID> Pn.k` — the concrete next command.
- **Done:** · **Remaining:** · **Sources of truth:** (plan.md, phases/Pn.md, key files) · **Open risks:**
- **Workarounds/Deferred/Open questions:** keys match run-report
  `devloop{workarounds,deferred,open_questions}` — cross-checkable with telemetry.

Under a master plan the general session handoff (skill `session-handoff`) collapses
here — do not keep a second handoff file.

**"item/phase → handoff → /clear" cycle:** after handoff.md is overwritten, `/clear`
is recommended — the next item starts from reading the plan (plan.md → phases/Pn.md →
handoff.md), not the chat tail. plan-exec and plan-close print the fixed reminder line:
`Context: handoff свежий — рекомендован /clear перед следующим item`.

## 7. Routing & Thinking Policy (SSOT matrix)

Default role→model/effort routing. Plan section `## 3. Routing` stores ONLY deviations:

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

## 8. Escalation (cheap-model protocol)

Triggers — closed enum:

- multi-package refactoring · unclear architecture · public contract/SemVer ·
  protected generated assets · rule conflict · unclear acceptance

On trigger the executor leaves THREE greppable artifacts:

1. Blockquote in the item:
   `> 🔴 ESCALATION Pn.m: <причина> | trigger: <из enum> | нужен: plan-design`
2. `**Status:** 🔴 Blocked` on the item.
3. Final report line: `ESCALATION-REQUIRED: Pn.m — <причина>`.

Plan diverged from code → do NOT improvise, escalate: plan-design fixes the plan,
not the executor on the fly.

## 9. Command protocol

| Command | Model/effort | Does |
|:--|:--|:--|
| `/task:plan-design` | opus/high | new plan / new phase / item specs |
| `/task:plan-exec` | sonnet/medium | execute an item; self-closing (updates statuses + handoff) |
| `/task:plan-close` | sonnet/low | status reconciliation / phase close |
| `/task:plan-audit` | opus/xhigh | adversarial phase audit; verdict GREEN/ATTENTION/RED |

## 10. Plan-quality checklist

- [ ] Every item executable by sonnet with no context beyond the plan.
- [ ] Required Reads finite and ordered (not "look around the repo").
- [ ] Code Guidance filled for every item (not «—»).
- [ ] Phase-first: phases close sequentially, items don't jump between phases.
- [ ] `plan-lint` green.

## 11. Per-project deployment

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

## 12. Plan artifacts: findings/

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

## 13. Related skills

- `task-brief-template` (general) — single task without a master plan.
- `session-handoff` (general) — arbitrary-session handoff; under a master plan the handoff lives in `plans/<ID>/handoff.md`.
- `complex-task-orchestrator` (general) — decomposition and context routing.
- `context-economy` (general) — Plan→Clear→Execute, token discipline.
- `anti-drift` (general) — executor iteration discipline, circuit breaker.

<!-- ru-source-sha256: 458dd3c9d74d3ca56146337d1e8ba3089907f3e4147e1ff46156159c05867382 -->
