# P3 runtime read topology refinement

## Sources and boundary

This synthesis consumes `findings/23-p3-runtime-design-preflight-2026-08-14.md`,
`findings/07-p3-control-plane-recon-2026-08-02.md`,
`findings/P0-provider-fleet-baseline.md`,
`research/03-p3-control-plane-implementation-design.md`,
`research/09-fleet-migration-classification.md`, D39, D42, D57, D59, D60 and the
frozen P1/P2 contracts. It changes only execution read topology and validation ownership;
provider-control-plane, Skill Core, adapter, evidence, locale and migration semantics remain
frozen. RAG:— (repo-grounded: the named carriers and D72's accepted compact-read precedent).

## P3.2 seam map

The root coordinator reads the frozen control-plane/Skill Core/adapter/evidence contracts,
P3 reconnaissance, P3.1 state, D39 package-cwd protocol and the shared
`registry`/`artifact`/`lock` boundaries. It does not preload four package implementations into
one context. Each fresh package cwd reads root→package instructions and only its own exact
`Files` slice before mutation, then returns the D39 evidence record. This isolates reads by
owner without changing the files that must be understood or validated.

The public relative-target failure is not a core lock defect: Harness normalizes a user-facing
target to an explicit absolute root before calling the shared lock planner. Relative and absolute
dry-runs must produce the same plan identity and operation identities/statuses with zero writes.

## P3.3 finite policy input

P3.3 implements frozen status/diagnostic schemas and finite classification/refusal policy; it
does not process 13,421 fleet rows. The compact sealed sources already state the only observed
P0 classes (`ambiguous=13319`, `broken-link=102`), the known-case counts, no-write disposition,
privacy boundary and source-machine carrier. The frozen control-plane contract owns the complete
action/refusal vocabulary. The 11.7 MiB row corpus remains authoritative evidence for P5 exact
fleet actions and is deliberately not a P3 runtime input.

Package implementation reads are again slice-local under D39. The root coordinator consumes
P3.2 readback, frozen contracts, compact P0 baseline/classification carriers and the accepted
D59/D60 signal/measurement decisions; it integrates the returned package records and runs the
cross-package acceptance suite.

## Anti-displacement verdict

The read-budget pass must not come only from splitting or hiding work. Two distinct changes are
made:

1. a genuine semantic reduction removes fleet row data that P3 neither interprets nor mutates;
   P5 remains its owning consumer;
2. D39 owner isolation prevents one root from rereading every package implementation, while each
   package slice still reads and validates its exact changed files under its own rules.

No validation command, frozen contract, package guide, target file set, provider row, readback
gate or cross-provider negative is removed. The post-edit machine measurements below are recorded in
the final design receipt after each design gate has passed.

## Measured result

Worktree-local `task.plan_weight` with `token-estimate-calibration v2.0.0`
(`codex/gpt-5.6-terra`) produced:

| Measure | Before | After |
|:--|--:|--:|
| P3.2 mandatory-read weight | 125817 | 66051 |
| P3.3 mandatory-read weight | 3408343 | 48262 |
| P3.1–P3.3 subtotal | 3613436 | 193610 |
| whole-plan closed-graph aggregate | 27786686 | 24366860 |

The aggregate reduction is `3419826` estimated tokens. Both edited items are
`admission_state=ready`, `admission_pass=true`, have zero read gaps, and are below the
`100000` item ceiling. Prospective stdout bundles resolve every declared entry: P3.2 has 44
entry references / 63,580 unique-path estimated tokens / 22,649 serialized bytes; P3.3 has 42 /
42,755 / 22,961 respectively. They remain deferred on disk until predecessor terminality so a
P3.1/P3.2 state change cannot make a persisted future bundle stale.

The plan still contains larger later items because their full fleet/corpus inputs remain owned by
their actual execution phases. P3 acceptance does not claim those future read graphs green.
