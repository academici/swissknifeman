# Read-budget gate

`plan-lint` applies `read-budget` v1 only to executable plans declared with `Layout | v2`.
For each `ready` item, `task.plan_gates` delegates the mandatory-read graph and weight to
`task.plan_weight`, and timing/producer semantics to `task.plan_admission`.

The gate rejects a weight above the plan-owned D2(a) threshold, every unreadable or unresolved
mandatory input, and every file over either measured `read-limit` boundary.  Missing or invalid
calibration, read-limit, and threshold-contract inputs are errors.  Layout v1 remains completely
outside the gate; it has no opt-in, warning mode, or baseline.
