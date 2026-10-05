---
disable-model-invocation: true
description: "Read-only Task plan audit of a design or a phase on explicit owner request."
argument-hint: "<PLAN> <Pn|design>"
model: opus
effort: xhigh
---
Invocation payload: `$ARGUMENTS`. `plan.py` is `python3 <Task package root>/scripts/plan.py`.

**Goal:** one independent verdict (GREEN / ATTENTION / RED) on a plan design or a finished phase.

**Steps**
1. `plan.py check <plan>` and `plan.py show <plan>`; read the target phase and items with
   `plan.py show <plan> <ref>`.
2. `design`: judge whether each detailed item is executable from its context pack
   (`plan.py context <plan> <item> --stdout`): scope, reads, exact checks, decisions, dependencies.
3. `Pn`: compare the phase's product diff with item scope, recorded checks and deliverables; rerun
   only checks whose inputs changed.
4. Write the verdict to `@plan/artifacts/audit/<Pn|design>-<YYYY-MM-DD>.md`: verdict, findings
   (severity, evidence `path:line`, owning item), recommendations.
5. `plan.py log <plan> <Pn> --type note --summary "audit <verdict>: <file>"` (`design`: the first target phase).

**Rules**
- Runs only on explicit owner invocation; one reviewer, one pass, no subagents unless asked.
- Read-only over product code and plan JSON; the verdict file and the note are the only writes.
- A finding names its owning item; fixing it is `plan-run` work (`plan.py reopen` by the owner).
- Severity follows demonstrated impact; uncertainty is reported as a question, not a defect.

**Done when** the verdict file exists, the note is logged, and the report gives the verdict and
`plan.py next <plan>`.
