# Acceptance Protocol v1.1.2

**Contract ID:** `acceptance-protocol`
**Version:** `1.1.2`
**Status:** frozen
**Frozen by:** `2026.08.07-PLAN-ECONOMY P6.9`
**Machine source of truth:**
[`acceptance-protocol-v1.manifest.json`](acceptance-protocol-v1.manifest.json)

Version 1.1.2 is frozen before the repeated acceptance arms or session canary are run. It preserves
the thresholds, qualified unit, scope traversal, admission reducer, arms, anti-displacement
controls, roles, confounds, exact canary branches and measurement implementation from v1.1.1. The
only changes are successor identity, D158 owner provenance and the appended v1.1.1 prior result.

## Prior results

Version v1.0.0 remains immutable and **RED**. Its report is
`findings/12-p6-acceptance-measurement.md`; the frozen Markdown SHA-256 is
`a3faa776d1fd659f1751a0d1c132bffcaec9add230cb087fa54417a50949d8c0` and the manifest SHA-256 is
`9ec184b15e6319c0f2af299a649f77f2a59c249a87206d590e866ed5c2cf530b` at commit `48522653`.
This version neither renames that result nor recomputes it under the new reducer.

Version v1.1.0 remains immutable and **NOT-RUN** as an acceptance attempt. Its preflight proved
that the pinned production implementation measured the legacy path rather than the declared five
layout-v2 slots, so arm A was prohibited before evidence capture. Its report is
`findings/P6.8-retry-preflight-2026-08-09.md`; the frozen Markdown SHA-256 is
`89ad3e23e7050534c1c2a9eb86b7f6d27ea178e48c84b6be95d70f702b571d9d` and the manifest SHA-256 is
`ff4926e7e98a7dbf979791fa44d55531326439e32b3a984881374c58b22fb476` at commit `536a1b3e`.

Version v1.1.1 remains immutable and **fail**. Its arm-A raw SHA-256 is
`48c00b9a0dca8e238627d5d7193527379957831935c33fae6e9c2185ecb7ade8`; the frozen contract and
manifest SHA-256 values are respectively `2491a99f9b52d807f1e2871e7e6a2cdd5f7497a3c725a78947b7247d4a859748`
and `42b834d84c95178cb971aa26c09588ac97639b9d831111b3a8bd74a5b0ef4b01`. Its 30/30 ready failures
and stop-after-arm-A outcome are not recomputed or renamed by v1.1.2.

## Measurement

The production measurement command is the manifest's `measurement.command`. It invokes the
worktree-local `plan-weight.py plan` path and emits its stable `plan-weight-v1` JSON. The qualified
unit is the upper-bound token estimate from calibration v2 for the pinned Codex target and probe
protocol. The independent whole-file byte and rendered-read token limits come from `read-limit` v1.
Their artifact paths, content hashes, and the read-path specification hash are frozen in the
manifest; a different provider, model, calibration, path specification, or command is a different
protocol version.

Version 1.1.2 retains the production module commit `c0ee730c`, module SHA-256
`0a119876ac69a2e3e73a459f5b02741ef085d1b4af1f81fecb0d5ff51e8c1c07`, and launcher SHA-256
`c678c28268759b55d455e7422f360f02bc9fcd1983a4216dd4447895c2428ce1`. This identifies the
implementation without changing the command, formulas, scope, or adjudication.

The caller supplies only `ACCEPTANCE_PLAN_DIR`. Raw command output is retained with each arm.
Derived acceptance fields use the formulas in `measurement.derived_metrics`; they are not selected
by judgement at measurement time. Raw totals remain observations, while hard verdict metrics and
coverage are also reported separately for each admission state.

## Scope manifest

The machine `scope_manifest` is normative. Measurement begins at every item specification, resolves
the five layout-v2 executor slots through `read-path` v1, and follows only digest-qualified bundle
entries. Generated carriers are included from their committed bytes and must be fresh. Calibration
overhead is applied to each file occurrence on each item path. The aggregate is the sum of complete
mandatory item-path weights, so moving a carrier or splitting an item cannot erase the total work.

Only carriers absent from every executor path and every selected bundle entry are excluded.
Owner-, designer-, history-, and audit-only carriers remain excluded unless an item explicitly
declares one through its bundle. Missing, unreadable, stale, ambiguous, or undeclared ready inputs
fail closed. Cache hits, deferred work, links, and external stores never reduce measured work.

## Stage-aware admission and verdict

Every measured item has exactly one closed admission state:

- `ready` participates in the hard verdict and requires `admission_pass=true`, `d2a_pass=true`,
  `d2b_pass=true`, and zero admission gaps;
- `historical-pre-v2` retains `null` gates and is published as **evidence-only**; it can produce
  neither a hard pass nor a hard fail;
- `pending-producer` retains `null` gates and is **deferred** until its declared producer output is
  available; while any pending producer remains, final pass is forbidden.

The reducer is deterministic and ordered: any ready failure yields `fail`; otherwise any
`pending-producer` yields `deferred`; otherwise all ready items being green yields `pass`.
An unknown or fourth state fails closed. Historical maximums and gaps remain visible evidence but
never enter the hard reducer. Coverage is reported separately for all three states; combined raw
coverage is observation only.

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

The mechanical test is the manifest's invariant traversal, aggregate comparison, state-separated
scope coverage, ready-item admission gaps, and independent whole-file guards. A positive or
unresolved answer is failure. A ready primary-threshold failure, incomplete ready scope, invalid
ready input, stale generated carrier, merged arm result, protocol drift, or session-canary mismatch
is also failure. Historical evidence cannot create or conceal a hard outcome; pending producer
evidence makes the result deferred. Retrofitting the threshold, exclusions, formulas, states, or
expected branches is forbidden.

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

Any edit after the v1.1.2 acceptance command is run is forbidden by the one-shot D158 mandate.
P6.9 must terminalize the observed result; a later successor would require a new explicit owner
decision and a new plan, while preserving every earlier result with its report and hashes.
