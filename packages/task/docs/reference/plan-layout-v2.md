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
byte drift. A migrated plan carries its legacy version in a converter
provenance marker, so `status.md` can render that value without inventing it.

## Migrating a plan

`plan-migrate.py` deterministically converts a legacy v1 plan to v2. In-place
migration is deliberately restricted to the approved self-host plan; every
other source may only be read through an explicit dry run and a new output
directory. Git remains the rollback mechanism.

```bash
# approved self-host plan only
python3 packages/task/scripts/plan-migrate.py plans/<SELF-HOST-PLAN>

# any other plan: source stays byte-identical
python3 packages/task/scripts/plan-migrate.py plans/<SOURCE> --dry-run --output /tmp/<projection>
```

The converter writes a generated migration inventory and before/after read-weight
evidence. A legacy source without `## Обсуждение` is valid: the inventory records
that the optional carrier was absent and no replacement discussion file is
invented. When the final journal position is blocked, the projection materializes
the required v2 escalation marker from that journal state. Re-running it on an
already migrated plan must not change bytes; use the normal `plan-views ...
--check` commands to verify generated carriers.

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

## Terminal phase closure

A terminal phase remains at `phases/Pn/Pn.md`; it is never moved to an archive directory. Its
generated design-facing digest is `phases/Pn/Pn.closed.md`. The resolver excludes terminal phases
from executor, designer, and owner live paths, while the auditor can still address their original
carriers. A closure build for a live phase must refuse rather than emit a provisional file.

## Decisions and generated views

Decision truth lives in immutable `decisions/D<NNN>-<slug>.md` records. Their
four derived navigation files — `_current.md`, `_archive.md`, `_index.md`, and
root-level `open-questions.md` — are generated through
`python3 packages/task/scripts/plan-views.py decisions --plan-dir <plan>`.
Use `--check` in automation; it regenerates in memory and rejects any byte
drift. A v2 `## 5. Decision Log` is only a pointer to that catalog and command;
`## Обсуждение` is replaced by the proposed-decision view.

## Linter continuity

`configs/lint-check-dispositions.json` records the layout-v2 disposition of
every module-local `_lint_*` check. The accompanying test derives that set by
introspection, so a newly added check without a disposition fails validation.
Checks whose old carrier disappeared retain their meaning by reading v2
decision records and `journal.jsonl`: decision RAG markers, replacement
`Consequences`, and the Update Log length limit do not silently disappear.

## Bundle input manifest

Build the deterministic, committed manifest for every item with
`python3 packages/task/scripts/plan-views.py bundle --plan-dir <plan> --all`.
Use `--item Pn.m --stdout` to inspect one manifest and `--check` to reject byte
drift. The producer reuses the declared-input resolver, validates the result
against the lifted Bundle v1 schema, and refuses atomically when a declaration
cannot resolve; the P3.4 gate later reports that condition as
`unresolvable_entry`.
