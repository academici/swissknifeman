---
name: workflow-craft
bucket: general
version: 0.1.0
description: "Activate on \"write a workflow\"/multi-agent orchestration: match 4 canonical templates first, then design-vs-dev stage matrix; slots per README."
risk: draft
persona: oss-dev
tags: [workflow, orchestration, multi-agent, templates, authoring]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Workflow-craft

A thin pointer skill to the canonical workflow-template constructor
(`packages/task/workflows/`). This is DISCIPLINE for activation and choice,
NOT a copy of template contents — template bodies and slot rules live in
`packages/task/workflows/README.md`; this skill points to them.

## When to activate

Use this skill when the user asks for:

- "write/compose/generate a workflow", "orchestrate subagents", "multi-agent
  run", "run several agents in parallel";
- authoring a `*.js` script for the Workflow tool (`scriptPath`/named-workflow);
- reworking/extending an already-existing plan workflow script.

**Field-case this skill closes:** a project is connected to skiller, the
constructor exists and its dev template already has mandatory review — and
the model still invents orchestration from scratch for a free-form phrasing
("compose a full-development workflow") and drops the mandatory review stage.
A free-form phrasing doesn't match any existing trigger — this skill's
`description` is the missing trigger.

**Boundary vs neighboring skills (don't blend):**

- `complex-task-orchestrator` — decomposing a task IN GENERAL (layers,
  invariants, DoD) inside ONE agent session, without spawning a separate
  `*.js` script and without launching subagents via the Workflow tool. If the
  output is an in-session action plan, not a workflow-script file — that's
  the other skill, not this one.
- `plan-protocol` — master-plan format and lifecycle (`plans/<ID>/`, phases,
  statuses, DoR/DoD). A master plan MAY spawn a workflow script for its
  execution phase (see "File location and name" below) — but the plan itself
  isn't about subagent orchestration, it's about framing the work.
- `/task:make-workflow` (gate command, if present) — interview + generation +
  automatic output reviewer around this same discipline. If the command is
  available, prefer it over manually following the skill: it guarantees a red
  reviewer verdict blocks the script from shipping unfixed.

## Procedure (in this order, don't reorder)

### 1. Match the 4 canonical templates first

Open `packages/task/workflows/README.md` — 4 parameterizable templates:
`wf-research-fanout.js`, `wf-author-by-spec.js`, `wf-audit-adversarial.js`,
`wf-dev-slice.js`. The constructor is a **library of portable templates, not
a code generator**: a task almost always fits one template or a pipeline of
several (research-fanout → author-by-spec/dev-slice → audit-adversarial).
Copy the matching template into the owning plan's `plans/<ID>/workflows/` and
fill the slots. If a task truly doesn't fit any template or their combination
— that's a deliberate exception (expensive-model main loop), not license to
silently write orchestration from scratch.

### 2. Mandatory stages by task type (SSOT matrix)

Workflows come in exactly two types, each with its own fixed set of mandatory
stages. Blending types or dropping a mandatory stage is a defect even if the
user didn't explicitly ask for it out loud (review for a dev workflow isn't
an interview question, it's a given).

| Type | Base templates | Mandatory stages | What's absent |
|:--|:--|:--|:--|
| **Design** (design-only) | `wf-research-fanout.js`, `wf-audit-adversarial.js` | RAG research → design (expensive-model main loop) → adversarial audit/DoR gate → fixes → re-audit | code, tests, semver |
| **Development** (dev) | `wf-dev-slice.js`, `wf-author-by-spec.js` | slice → impl → tests-to-green → risk-adaptive review → inter-slice gates → commit | design decisions on the cheap model (escalate to main loop, don't decide inline) |

This table is the skill's SSOT — the `/task:make-workflow` command and its
output reviewer cite THIS table, not their own copy; fix drift here only.

**Don't invent mandatory stages beyond this table** (source: `roadmap/
workflow-craft.md` §1.5 + `packages/task/workflows/README.md`) — if it seems
like another mandatory stage is needed, propose a matrix edit explicitly,
don't quietly bolt it onto one script.

**design ≠ dev, don't blend.** These are two disjoint requirement sets, not
two variants of one set: a design-only script with an `impl`/`tests` step, or
a dev script without risk-adaptive review, are equally defective (the first
turns a design session into unplanned code on the cheap model, the second
reproduces the exact vaulter field-case). Determine the type BEFORE
generation (the template-matching step already hints the type:
research-fanout/audit-adversarial → design-only, dev-slice/author-by-spec →
dev) and run the whole script down one column of the table — don't mix in
stages from the other column "just in case".

### 2.1 Reference scripts (field prototypes of both types)

Two real workflow scripts from other plans in vault Brain serve as a shape
reference (stage structure, what each type does NOT contain) — **cross-ref by
absolute path, don't vendor** (they belong to other plans; a copy drifts from
the source):

- **design-only:** `/home/vostrikov/Vaults/Brain/plans/ECOSYSTEM/workflows/
  wf-design-fleet.js` — RAG research → design → adversarial audit/DoR gate →
  fixes → re-audit, with zero lines of code/tests.
- **dev:** `/home/vostrikov/Vaults/Brain/plans/AGENTOOLS/workflows/
  wf-agentools-drive.js` — slice → impl → tests-to-green → review → gates →
  commit, with a `designOnly` slot flag branching between the two modes
  within one template family.

If the file is unreachable (vault not mounted on the executing machine) —
don't fail and don't invent content: use the path as a cross-ref only and the
table above as the requirement source.

### 3. Slot rules — by reference, don't duplicate

How to fill slots (constants in the script header, embedded config instead of
an args string, structured-summary-by-schema for every `agent()`, judge-panel
only for high-stakes, max-iteration on every loop-until) — see
`packages/task/workflows/README.md` §"Slot-filling rules". Started retelling
these rules here instead of linking — stop, that's a constructor duplicate.

### 4. File location and name

The script is an artifact of the owning plan: `plans/<ID>/workflows/wf-<plan-
id-lower>-<purpose>.js`, not a free location in the repo. If the task isn't
tied to a master plan (a one-off run outside `plans/`) that's an exception,
but the canon is mandatory whenever a plan exists (see `plan-protocol` — the
"two homes" scheme).

### 4.1 Anti-relaunch discipline (co-developing a workflow inside a session)

The run-report field `workflow_relaunch` (harness detector `_lib.py`, fires at
≥3 launches/resumes of one workflow in one session) is not a core-tool bug:
`resumeFromRunId` after an `Edit` to the script is a documented, sanctioned
pattern ("the longest unchanged prefix of agent() calls returns cached
results instantly"). Field precedent (`plans/2026.07.15-TELEMETRY-OPT/
findings/P1-workflow-rootcause.md`): a dterema session called `Workflow` 15×
in a row — not "relaunch without a signal", but **8 rounds of fixing the
workflow script from inside the main interactive session** (relative-path
bug, top-level `return`, gate prompt missing scope, docblock/formatting,
review-prompt text fixed twice), each fix → commit → `resumeFromRunId`. The
signal is a diagnostic proxy — "script was written and fanned out untested" —
not an alarm.

**Rule:** before calling `Workflow` on a script you just wrote or heavily
edited, dry-run its syntax/logic on a minimal data slice (or at least
`node --check`) in an isolated dev-loop, rather than treating the fan-out
itself as your linter. If `workflow_relaunch` still fires (many resumes on
one script this session) — that's not cause for alarm (the process is
sanctioned), but it IS cause to fix one bug per resume deliberately rather
than silently piling up iterations: note in the script comment what each fix
addressed, so `analyst digest` (candidate lesson `workflow-relaunch`) and the
next session see the fix history, not just the final version.

### 5. RAG option for non-standard orchestration

If the task needs orchestration the 4 templates don't cover directly (rare,
not the first choice) — before inventing a pattern from scratch, check
current practice via `research/query-craft` (how to phrase the query) →
`general/verify-claims` (when/how to verify). Mark the result in the script
comment: `RAG:✅ <date> <source>` or `[UNVERIFIED]` if the engine was
unavailable — don't pass off unverified orchestration as verified.

## Checklist before shipping a script

- [ ] Task checked against the 4 templates first — not written from scratch
      if it fits.
- [ ] Type determined (design-only / dev), matrix's mandatory stages present.
- [ ] Slot rules followed (constants, embedded config, structured-summary,
      max-iteration) — per README, not from memory.
- [ ] File location and name — canon `plans/<ID>/workflows/wf-<id>-
      <purpose>.js`.
- [ ] Non-standard orchestration marked RAG:✅/[UNVERIFIED].

## Related skills

- `general/complex-task-orchestrator` — decomposing a task within one session
  without spawning a separate workflow script (boundary above).
- `general/plan-protocol` — master-plan format; the workflow script is an
  artifact of the plan's execution phase, "two homes" sets its canonical
  location.
- `general/spec-interview` — the "one question at a time" mechanic used by
  the `/task:make-workflow` gate command when clarifying template slots.
- `research/query-craft` — how to phrase a RAG query for non-standard
  orchestration (step 5).
- `general/verify-claims` — when and how to verify an external fact at all.

<!-- ru-source-sha256: 87bd0d13768d91376e2f46ccf0f2352a061e1c2bdb7c203b890d4c48712545fb -->
