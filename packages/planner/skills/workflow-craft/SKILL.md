---
name: workflow-craft
bucket: general
version: 0.3.0
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
(the Task package's `workflows/`). This is DISCIPLINE for activation and choice,
NOT a copy of template contents — template bodies and slot rules live in
the Task package's `workflows/README.md`; this skill points to them.

## When to activate

Use this skill when the user asks for:

- "write/compose/generate a workflow", "orchestrate subagents", "multi-agent
  run", "run several agents in parallel";
- authoring a `*.js` script for the Workflow tool (`scriptPath`/named-workflow);
- reworking/extending an already-existing plan workflow script.

**Field-case this skill closes:** a project is connected to skiller, the
constructor exists and its dev template already has optional review — and
the model still invents orchestration from scratch for a free-form phrasing
("compose a full-development workflow") and drops the optional review stage.
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
- `/planner:make-workflow` (gate command, if present) — interview + generation +
  requested output reviewer around this same discipline. If the command is
  available, prefer it over manually following the skill: it guarantees a red
  reviewer verdict blocks the script from shipping unfixed.

## Procedure (in this order, don't reorder)

### 1. Match the 4 canonical templates first

Open the Task package's `workflows/README.md` — 4 parameterizable templates:
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
user didn't explicitly ask for it out loud (review for a dev workflow is
enabled only by explicit owner request).

| Type | Base templates | Mandatory stages | What's absent |
|:--|:--|:--|:--|
| **Design** (design-only) | `wf-research-fanout.js`, `wf-audit-adversarial.js` | RAG research → design (expensive-model main loop) → self-check/DoR gate → optional requested read-only audit → one owning correction; re-audit only after changed evidence | code, tests, semver |
| **Development** (dev) | `wf-dev-slice.js`, `wf-author-by-spec.js` | slice → impl → tests-to-green → optional requested review → inter-slice gates → commit | design decisions on the cheap model (escalate to main loop, don't decide inline) |

This table is the skill's SSOT — the `/planner:make-workflow` command and its
output reviewer cite THIS table, not their own copy; fix drift here only.

Review and audit are opt-in: hard risks widen self-checks, not review admission. An explicit review
request can optionally select `--reviewer provider/model`; otherwise use the current native route.
Execution and review are separate calls, never recursive unbounded
fix/review. One owner `plan-run --reviewer` invocation may orchestrate both roles automatically,
retaining their independent sessions and bounded verdict history. The reviewer never repairs
product or starts its successor. Fill reviewer slots from the selected or current captured native route before
requested review; do not silently pick a default model. Repeated systemic class/area findings revise the
shared invariant model, and completed review rounds are bounded by Task's two-completed-round/one-correction policy. A
resume retains review history and unchanged evidence; it never resets a cap or broad-replays
previously accepted work. See the workflow README for slot details.

**Don't invent mandatory stages beyond this table** (source: the Task package's `workflows/README.md`) — if it seems
like another mandatory stage is needed, propose a matrix edit explicitly,
don't quietly bolt it onto one script.

**design ≠ dev, don't blend.** These are two disjoint requirement sets, not
two variants of one set: a design-only script with an `impl`/`tests` step, or
a dev script that omits explicitly requested review, are equally defective (the first
turns a design session into unplanned code on the cheap model, the second
reproduces the exact vaulter field-case). Determine the type BEFORE
generation (the template-matching step already hints the type:
research-fanout/audit-adversarial → design-only, dev-slice/author-by-spec →
dev) and run the whole script down one column of the table — don't mix in
stages from the other column "just in case".

### 2.1 Reference scripts (field prototypes of both types)

Real workflow scripts from other plans in vault Brain serve as a shape
reference (stage structure, what each type does NOT contain) — **cross-ref by
absolute path, don't vendor** (they belong to other plans; a copy drifts from
the source):

- **design-only, high-water-mark:** `~/Vaults/Brain/plans/
  EDUFY-2/workflows/wf-edufy-2-design-wave.js` — the strongest live example
  surveyed (findings P1-recon §1.4 "Reference irony"): `// SLOT:` markers on
  every constant (the only one of ~44 fleet files carrying them), judge-panel
  gated ONLY on the high-stakes phase (`JUDGE_PHASES`/`JUDGE_QUORUM`, not
  everywhere), `MAX_FIX_ROUNDS` on EVERY audit→fix cycle (not just the main
  one), pipeline + phase dependency graph. Look at its structure FIRST — it's
  above the baseline of the two references below.
- **design-only, baseline:** `~/Vaults/Brain/plans/ECOSYSTEM/
  workflows/wf-design-fleet.js` — RAG research → design → adversarial
  audit/DoR gate → fixes → re-audit, with zero lines of code/tests.
- **dev, baseline:** `~/Vaults/Brain/plans/AGENTOOLS/workflows/
  wf-agentools-drive.js` — slice → impl → tests-to-green → review → gates →
  commit, with a `designOnly` slot flag branching between the two modes
  within one template family; L195 is a guarded-optional-args example
  (`typeof args === 'string' ? JSON.parse(args) : (args || {})`).

If the file is unreachable (vault not mounted on the executing machine) —
don't fail and don't invent content: use the path as a cross-ref only and the
table above as the requirement source.

### 3. Slot rules — by reference, don't duplicate

How to fill slots (constants in the script header, `// SLOT:` markers
recommended but not mandatory; embedded config instead of an args string;
structured-summary-by-schema for **control-flow agents**, action/mechanical
agents may return prose; judge-panel only for high-stakes; max-iteration on
every loop-until; top-level `return report` is a sanctioned runtime idiom, not
a defect) — see the Task package's `workflows/README.md` §"Slot-filling rules".
Started retelling these rules here instead of linking — stop, that's a
constructor duplicate.

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
results instantly"). Field precedent (
): a dterema session called `Workflow` 15×
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

**Checkpoint before a third resume in a row: is my cache-bust marker
global?** A second field precedent on the same project/script (`dterema`,
`wf-dterema-site-p3-api.js`, 2026-07-15) burned ≈4M subagent tokens in one
day: the script held ONE global `GATE_ASOF` constant pasted into the code-gate,
bookkeeping-gate and review prompts of EVERY pipeline item. Each bump — made to
re-verify a SINGLE item being fixed — invalidated the `agent()` cache for
already-closed items too, so the resume re-ran gate+review over files that
hadn't changed by a line. Rule: a manual invalidator is a **per-item field
only** (`s.asOf`, mixed into that item's prompt/`label` — see README "slot
rules" → per-item cache-bust), never a global constant across all prompts.
Better still, no manual marker: the gate prompt already asks the agent to check
`git log`/HEAD, so freshness is verified live; forcing is needed only after an
external fix commit and must stay local.

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
  the `/planner:make-workflow` gate command when clarifying template slots.
- `research/query-craft` — how to phrase a RAG query for non-standard
  orchestration (step 5).
- `general/verify-claims` — when and how to verify an external fact at all.
