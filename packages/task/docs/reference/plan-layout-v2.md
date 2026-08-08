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

## Stable core and owner status view

In v2 `plan.md` contains only `## 0. Meta` identity and registrar fields,
`## 1. Context`, `## 2. Execution Rules`, `## 3. Routing`, the `## 5. Decision
Log` pointer, and optional `## 7. Contracts`. `Version`, `Status`, and `Last
Updated`, together with the phase board and update log, are absent from the
core. `Design Passes` and `visibility` remain in the Meta table: both are slow
registrar fields, not item-closure state.

`status.md` is the generated owner view. Build or verify it with:

```bash
python3 packages/task/scripts/plan-views.py status --plan-dir <plan-dir> [--check]
```

The projector derives item and phase status from v2 state carriers and its
Update Log from `journal.jsonl`; `--check` regenerates in memory and rejects
byte drift. Until the v1→v2 migrator lands in P2.8, a new v2 fixture has no
source for the legacy plan-version value, so the view explicitly renders `—`
instead of inventing a version.

## Item-state projection

Build or verify every adjacent generated state carrier with:

```bash
python3 packages/task/scripts/plan-views.py state --plan-dir <plan-dir> --all [--check]
```

The reducer derives the five outcome fields from the append-only journal and
validates its closed model against `configs/item-state-projection-v1.schema.json`.
It rejects unknown results and never emits routing data; `--check` rejects byte drift.

## Item history projection

The auditor can assemble an item’s on-demand history from exactly the sealed journal,
immutable decision records, and item-scoped findings:

```bash
python3 packages/task/scripts/plan-views.py history --plan-dir <plan-dir> --item Pn.m
```

The default prints deterministic Markdown to stdout. To preserve audit evidence, pass an
explicit `--output`; `--check` is available only with that output and rejects byte drift.
The default cache address `.plan-cache/history/` is ignored by Git. The view is not an
authority: it has projection metadata and links facts chronologically, including superseded
decisions, without judging them.

## Decisions and generated views

Decision truth lives in immutable `decisions/D<NNN>-<slug>.md` records. Their
four derived navigation files — `_current.md`, `_archive.md`, `_index.md`, and
root-level `open-questions.md` — are generated through
`python3 packages/task/scripts/plan-views.py decisions --plan-dir <plan>`.
Use `--check` in automation; it regenerates in memory and rejects any byte
drift. A v2 `## 5. Decision Log` is only a pointer to that catalog and command;
`## Обсуждение` is replaced by the proposed-decision view.
