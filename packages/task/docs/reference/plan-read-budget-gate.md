# Read-budget gate

`plan-lint` applies `read-budget` v1 only to executable plans declared with `Layout | v2`.
For each `ready` item, `task.plan_gates` delegates the mandatory-read graph and weight to
`task.plan_weight`, and timing/producer semantics to `task.plan_admission`.

The gate rejects a weight above the plan-owned D2(a) threshold, every unreadable or unresolved
mandatory input, and every file over either measured `read-limit` boundary.  Missing or invalid
calibration, read-limit, and threshold-contract inputs are errors. Retired layouts remain completely
outside the gate; it has no opt-in, warning mode, or baseline.

For Layout v2, the measured executor path is exactly `plan-core`, `phase-context`, `item-spec`,
`item-input-bundle`, and `item-state`, followed by the digest-qualified selections declared by the
bundle. `handoff.md` is not an executor carrier in v2. Bundle and state projections must be
byte-fresh before measurement; a stale projection, a source/selection digest mismatch, or an
unresolvable selection fails closed.

## Bundle freshness

For selected-workset closure use `plan-lint.py plans/<ID> --item P4.2 --item P4.3`.
The scope includes recursive producer dependencies. Future-only `read-budget-v1` and `bundle-v1`
problems remain visible as `FUTURE_ITEM_NON_GATING` warnings. Current/producer findings and global
or unclassifiable failures remain errors. Unscoped lint and fleet CI/release remain full gates.

For `Layout | v2` that already carries at least one Bundle v1 in its active phase,
`plan-lint` checks every `ready` item in that phase. It rebuilds the expected manifest
in memory and reports declaration
drift as `stale_vs_spec`, absent records as `missing_entry`, changed source bytes as
`hash_mismatch`, and an unresolvable declared entry as `unresolvable_entry`. An extra
manifest entry is `extraneous_entry` and remains a warning. The lint never writes a
projection; use `plan-views.py bundle --item <Pn.m>` to materialize one deliberately.

The same gate invokes the owners of decision, status, and item-state projections in
their check-only mode. A broken decision supersession names both decision identifiers.

## Read-path declarations

For v2 plans, `plan-lint` reads the frozen carrier registry and read-path specification.
It rejects decreasing volatility across slots or declared carrier sections, a `history`
carrier on the executor path, and an active-phase item that names an item specification
from a terminal phase. These checks use carrier ids, classes, declared slots, and the
resolver’s phase status—not filename heuristics. References to a sibling item remain valid.
