# Acceptance Protocol v1

**Contract ID:** `acceptance-protocol`
**Version:** `1.0.0`
**Status:** frozen
**Frozen by:** `2026.08.07-PLAN-ECONOMY P6.7`
**Machine source of truth:**
[`acceptance-protocol-v1.manifest.json`](acceptance-protocol-v1.manifest.json)

This protocol is frozen before either acceptance arm or any observed session-canary result is
opened. During authoring, only the key/type shape of the existing migrated-arm artifact was read;
no arm value was inspected or copied into this contract.

## Measurement

The production measurement command is the manifest's `measurement.command`. It invokes the
worktree-local `plan-weight.py plan` path and emits its stable `plan-weight-v1` JSON. The qualified
unit is the upper-bound token estimate from calibration v2 for the pinned Codex target and probe
protocol. The independent whole-file byte and rendered-read token limits come from `read-limit` v1.
Their artifact paths, content hashes, and the read-path specification hash are frozen in the
manifest; a different provider, model, calibration, path specification, or command is a different
protocol version.

The caller supplies only `ACCEPTANCE_PLAN_DIR`. Raw command output is retained with each arm.
Derived acceptance fields use the formulas in `measurement.derived_metrics`; they are not selected
by judgement at measurement time.

## Scope manifest

The machine `scope_manifest` is normative. Measurement begins at every item specification, resolves
the five layout-v2 executor slots through `read-path` v1, and follows only digest-qualified bundle
entries. Generated carriers are included from their committed bytes and must be fresh. Calibration
overhead is applied to each file occurrence on each item path. The aggregate is the sum of complete
mandatory item-path weights, so moving a carrier or splitting an item cannot erase the total work.

Only carriers absent from every executor path and every selected bundle entry are excluded.
Owner-, designer-, history-, and audit-only carriers remain excluded unless an item explicitly
declares one through its bundle. Missing, unreadable, stale, ambiguous, or undeclared inputs fail
closed. Cache hits, deferred work, links, and external stores never reduce measured work.

## Thresholds and two arms

The exact thresholds and units are data in `thresholds` and are inherited from frozen
`read-budget` v1.1.0. They cannot be tuned after an outcome is observed.

- Arm A tests the narrow claim that conversion preserves or improves the same migrated artifact.
  Its frozen before/after evidence is the P2 migration artifact. No manual rewrite is allowed to
  manufacture a pass; every later intervention must be disclosed separately.
- Arm B tests only that the current `task:plan-design new` path can create a real plan satisfying
  this protocol. It does not establish migration improvement or natural unbiased authoring.

The arms are reported separately. Their values, pass states, and claims must never be averaged,
pooled, or collapsed into one number.

## Anti-displacement and failure

Acceptance reports the per-item maximum beside the closed-graph aggregate. For arm A, the aggregate
must demonstrate a real reduction against the frozen pre-conversion aggregate. Arm B has no
before-conversion comparison and therefore cannot make that claim; it must still preserve full
scope coverage and pass every primary and guardian metric.

Both arms must answer this question verbatim:

> Could this have passed exclusively by splitting, moving, caching, deferring, or excluding work?

The mechanical test is the manifest's invariant traversal, aggregate comparison, complete scope
coverage, unresolved-input count, and independent whole-file guards. A positive or unresolved
answer is failure. Any primary threshold failure, incomplete scope, unresolved input, stale
generated carrier, merged arm result, protocol drift, or session-canary mismatch is also failure.
The only outcome action is `escalate`: repair the instance or create a new contract version through
an owner decision. Retrofitting the threshold, exclusions, formulas, or expected branches is
forbidden.

## Roles and confounds

The instance author creates or migrates the plan but cannot change this protocol. The measurement
owner maintains the deterministic tool and its qualified artifacts but cannot adjudicate an
observed failure. The acceptance reviewer checks raw evidence, scope escape, and protocol identity;
for isolated-review canary branches the reviewer actor and route must differ from root.

Known confounds are declared in the manifest: authors know the metric; the same repository team
creates the instances; each arm remains a single internal case; Codex is the currently certified
provider row; and the migrated artifact may contain disclosed post-conversion evolution. The result
demonstrates internal feasibility only, not external validity, comparative superiority, or
population reliability.

## Session canary

`session_canary` is independent from both D2 arms. Its production command is the manifest-declared
`codex exec` path, parameterized only by explicit environment values and emitting JSONL evidence.
The four branch ids and expected maps are closed. Full root-path rereads do not include bounded
reviewer capsules; repeated-read bytes and tokens remain non-negative observations and are never
added to the D2 budget.

Missing or extra branches, aggregation, absent root provenance, reviewer provenance on the wrong
branch, the same actor on an isolated-review branch, an unapproved hard-boundary reason, or any
field mismatch fails the canary.

## Change control

Any edit after the first acceptance command is run requires reopening
`2026.08.07-PLAN-ECONOMY P6.7`, adding a linked D-record, assigning a new protocol version, and
downgrading every earlier pass claim. Silent amendment is never valid.
