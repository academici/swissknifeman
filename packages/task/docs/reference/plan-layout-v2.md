# Plan layout v2

`task.plan_layout` is the sole resolver for the two executable-plan layouts.
The frozen registry and read-path specification are copied byte-for-byte to
`packages/task/configs/`; missing `Layout` means v1. A v2 plan must declare
`Layout: v2` in Meta and keeps a phase at `phases/Pn/Pn.md`; item specifications
and state resolve to `phases/Pn/Pn.m.md` and `phases/Pn/Pn.m.state.md`.

## Phase and item carriers

`phases/Pn/Pn.md` is a thin phase index: it contains `## Phase Context` and
`## Phase Handoff`, never `## Phase Status` or an item block. Each `Pn.m.md`
contains exactly the handwritten specification fields: Intent, Why, Scope
Included, Scope Excluded, Inputs, Files, Required Reads, Implementation Rules,
Code Guidance, Validation, and Deliverables. The matching state carrier contains
exactly Status, Completion Notes, Pending Work, Known Deviations, and Escalation
Needed. The linter assembles both carriers into the existing 16-field item
model, so downstream consumers retain the same model shape.

An outcome field in an item specification, a specification field in a state
carrier, or a missing state carrier is an error. State files in fixtures are
test data only; P2.5 owns their generator.

Unsupported layout values and a declaration that disagrees with the physical
tree fail closed. Consumers must ask the resolver for carrier paths instead of
recreating `phases/`, `plan.md`, or `handoff.md` literals.

## Decisions and generated views

Decision truth lives in immutable `decisions/D<NNN>-<slug>.md` records. Their
four derived navigation files — `_current.md`, `_archive.md`, `_index.md`, and
root-level `open-questions.md` — are generated through
`python3 packages/task/scripts/plan-views.py decisions --plan-dir <plan>`.
Use `--check` in automation; it regenerates in memory and rejects any byte
drift. A v2 `## 5. Decision Log` is only a pointer to that catalog and command;
`## Обсуждение` is replaced by the proposed-decision view.
