---
disable-model-invocation: true
description: "Read-only planner plan audit of a design or a phase on explicit owner request."
argument-hint: "<PLAN> <Pn|design> [--reviewer <provider/model>] [--effort xhigh]"
---
Project CLI: `plan.py` means `python3 -I .swissknifeman/launcher.py planner`, run from the project root (the launcher binds the project; without one, run `swissknifeman project init` once). Never locate or run a Swiss Knife Man package script.
Owner rules: run `plan.py overlays planner:plan-audit` first and follow any rules it prints as additions to this command; they never override the plan, its checks or safety rules.
Invocation payload: `$ARGUMENTS`.

Read `references/reviewer-selection.md` for optional `--reviewer` and effort selection.
Without a selector, use the current native review route. A session that executed this candidate
must hand the review to a fresh read-only session; never review its own work as independent evidence.

**Goal:** one independent verdict (GREEN / ATTENTION / RED) on a plan design or a finished phase.

**Steps**
1. `plan.py check <plan>` and `plan.py show <plan>`; read the target phase and items with
   `plan.py show <plan> <ref>`.
2. `design`: judge whether each detailed item is executable from its context pack
   (`plan.py context <plan> <item> --stdout`): scope, reads, exact checks, decisions, dependencies.
3. `Pn`: compare the phase's product diff with item scope, recorded checks and deliverables; rerun
   only checks whose inputs changed.
4. Add a knowledge JSON document using `plan.py add-document <plan> --file <input.json>`:
   lowercase `id: audit-<scope>-<YYYY-MM-DD>`, title, `applies_to`, and `sections` for the verdict,
   findings (severity, evidence `path:line`, owning item) and recommendations. The API generates
   its human view; report the source `@plan/knowledge/<id>.json`.
5. `plan.py log <plan> <Pn> --type note --summary "audit <verdict>: <file>"` (`design`: the first target phase).

**Rules**
- Runs only on explicit owner invocation; one reviewer, one pass, no subagents unless asked.
- Read-only over product code and execution state; only the verdict document and note are added through the API.
- A finding names its owning item; fixing it is `plan-run` work (`plan.py reopen` by the owner).
- Severity follows demonstrated impact; uncertainty is reported as a question, not a defect.

**Done when** the verdict file exists, the note is logged, and the report gives the verdict and
`plan.py next <plan>`.
