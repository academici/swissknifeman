This is an internal self-hosted acceptance result for one migrated plan; it proves neither external validity nor population reliability, and arm A failed before arm B or the independent session canary was started.

# P6 acceptance measurement — 2026-08-09

## Verdict

`2026.08.07-PLAN-ECONOMY P6.8` is **RED** under frozen `acceptance-protocol` v1.0.0.
The migrated arm exceeded D2(a) and did not resolve the full declared graph. The protocol requires
all conditions, defines any one of these observations as failure, and permits only escalation after
failure. No threshold, exclusion, formula, source plan, or protocol carrier was edited.

Arm B and `session_canary` were not started after the decisive arm-A failure. They therefore have
no observed values and cannot be reported as passed, skipped-green, or averaged into arm A.

## Tree anchor and command

- repository `HEAD` at measurement: `c46a6aca17c8bdb8dd32f63f969532e7822168ab`;
- pre-output worktree patch SHA-256 (P6.8 start journal + generated state/status):
  `441214bdb05345e9342f65fa2c1810b7422da0d623c829e470cc5ef6cc940ef7`;
- raw evidence: `artifacts/P6/acceptance-arm-a-migrated.json`;
- protocol SHA-256: Markdown `a3faa776d1fd659f1751a0d1c132bffcaec9add230cb087fa54417a50949d8c0`,
  manifest `9ec184b15e6319c0f2af299a649f77f2a59c249a87206d590e866ed5c2cf530b`;
- command, executed exactly with only `ACCEPTANCE_PLAN_DIR` supplied:

  ```bash
  export ACCEPTANCE_PLAN_DIR='plans/2026.08.07-PLAN-ECONOMY'
  python3 packages/task/scripts/plan-weight.py plan "$ACCEPTANCE_PLAN_DIR" --json
  ```

The plan was already evolving after its P2 conversion. This disclosed post-conversion evolution
and the in-progress P6.8 state are confounds; neither changes the frozen pass predicates.
After measurement, P6.8 received only the protocol-required greppable escalation block. That
bookkeeping intervention is outside the anchored measurement, was not followed by a remeasurement,
and is not used to improve any reported number.

## Arm A — migrated plan

Claim tested: conversion preserves or improves the same migrated executable plan under the frozen
protocol.

| Metric | Observed | Frozen condition | Result |
|:--|--:|:--|:--|
| maximum item required-read weight | 101,744 qualified tokens (`P2.1`) | ≤100,000 | FAIL |
| closed-graph aggregate | 1,932,319 qualified tokens | current < 7,089,706 frozen before aggregate | PASS |
| aggregate reduction | 5,157,387 tokens (72.744723%) | real reduction | PASS |
| whole-file failures | 0 | 0 | PASS |
| unresolved inputs | 4 | 0 | FAIL |
| scope coverage | 43/47 = 0.9148936170 | 1.0 | FAIL |

The four unresolved inputs are preserved in raw evidence:

1. `P0.1`: prose-only unresolved entry for four test modules;
2. `P0.2`: prose-only unresolved directory entry for `packages/task/docs/reference/`;
3. `P1.5`: missing legacy path `phases/P0.md` after layout-v2 migration;
4. `P6.9`: missing future producer output `findings/12-p6-acceptance-measurement.md` at the
   measurement boundary.

The fourth gap is naturally produced by measuring before this report exists, but the frozen
failure definition has no exemption for it. Removing it after the fact would still leave the
101,744-token D2(a) failure and the other three unresolved inputs. The migrated instance was not
rewritten to manufacture a pass.

## Arm B — fresh plan

Not run. The frozen outcome was already RED, and `on_failure = escalate`; no fresh plan or arm-B
artifact was created. This is not evidence for or against the separate fresh-authoring claim.

## Session canary

Not run. No `session-canary-results.json` exists and none of the four branches is claimed as
observed. The independent canary remains unproven in this attempt.

## Anti-displacement answer

> Could this have passed exclusively by splitting, moving, caching, deferring, or excluding work?

**No pass occurred.** The invariant traversal still found a large aggregate reduction and no
whole-file violation, but complete coverage and D2(a) failed. Splitting or moving work cannot turn
this evidence into a pass because the report retains the closed-graph aggregate, unresolved-input
count, and per-item maximum together.

## Confounds and limits

- The authors knew the metric and threshold.
- The same repository team created and measured the instance.
- This is one internal migrated case (`n=1`) on the certified Codex row.
- The migrated tree contains disclosed evolution after conversion.
- Fail-fast means the fresh-authoring and session-continuity claims remain unmeasured, not failed.

## Required action

The acceptance protocol requires escalation. `2026.08.07-PLAN-ECONOMY P6.9` must not execute and
the ARTIFEX pause must remain. A later continuation needs a separately authorized instance repair
or a new acceptance-contract version; retrofitting the frozen threshold or exclusions is invalid.

## Attempt v1.1.1 — exact five-slot repair-pinned measurement

This is an internal self-hosted `n=1` result. It establishes neither external validity nor
population reliability. Frozen v1.1.1 was checked before execution: Markdown SHA-256
`2491a99f9b52d807f1e2871e7e6a2cdd5f7497a3c725a78947b7247d4a859748`, manifest SHA-256
`42b834d84c95178cb971aa26c09588ac97639b9d831111b3a8bd74a5b0ef4b01`, implementation commit
`c0ee730c`. The existing report prefix was preserved byte-for-byte (4,866 bytes, SHA-256
`6bfc5a14c492f6ead87435c7c34dfa3d39b2c5ff1a9a492b4eb16c441f123ff0`).

### Command and raw evidence

The manifest command was executed with only `ACCEPTANCE_PLAN_DIR` supplied:

```bash
export ACCEPTANCE_PLAN_DIR='plans/2026.08.07-PLAN-ECONOMY'
python3 packages/task/scripts/plan-weight.py plan "$ACCEPTANCE_PLAN_DIR" --json
```

Raw output is `artifacts/P6/acceptance-arm-a-migrated-v1.1.1.json`: 214,722 bytes,
SHA-256 `48c00b9a0dca8e238627d5d7193527379957831935c33fae6e9c2185ecb7ade8`, schema
`plan-weight-v1`. Observed roles are `plan-core`, `phase-context`, `item-spec`,
`item-input-bundle`, `bundle-input`, and `item-state`; `handoff` is absent.

### Arm A — migrated plan

| Metric | Observed | Frozen condition | Result |
|:--|--:|:--|:--|
| admission coverage | historical 17 · pending 0 · ready 30 | report separately | PASS |
| ready failures | 30/30 | 0 | **FAIL** |
| maximum item weight | 142,562 (`P6.5`) | ≤100,000 | **FAIL** |
| aggregate | 1,349,223 | current < 7,089,706 baseline | PASS |
| aggregate reduction | 5,740,483 (80.969267%) | real reduction | PASS |
| gaps | 88: missing 30 · unresolved 56 · oversized 2 | ready gaps 0 | **FAIL** |
| pending producers | 0 | 0 for final pass | PASS |

Failed ready ids: `P2.8`, `P2.9`, `P2.10`, `P3.1`–`P3.7`, `P4.1`–`P4.6`,
`P5.1`–`P5.5`, `P6.1`–`P6.9`. Exact traversal exposed absent historical/post-migration
bundles, stale generated bundle/state carriers, two oversized selected inputs, and D2(a)
violations. In particular the execution-start journal event made generated item states stale;
freshness is a frozen hard predicate, so this observation is retained as failure rather than
silently regenerated after seeing the raw result.

Reducer result: at least one ready failure exists, therefore arm A = **`fail`**. Precedence stops
before the pending branch or all-ready-green branch.

### Arm B and session canary

Not run. Frozen `on_failure=escalate` and D154 prohibit creating a fresh plan, arm-B artifact, or
`session-canary-results.json` after arm-A fail. Their absence is the required fail-fast outcome,
not a green or skipped measurement.

### Anti-displacement answer

> Could this have passed exclusively by splitting, moving, caching, deferring, or excluding work?

**No pass occurred.** The complete five-slot traversal retains aggregate, maximum, per-file and
freshness failures together. Aggregate reduction cannot compensate for 30 ready failures, so no
split/move/cache/exclusion interpretation can turn this attempt into pass.

### Final verdict and downstream gate

`2026.08.07-PLAN-ECONOMY P6.8` attempt v1.1.1 verdict is **`fail`**. P6.9 must remain
unexecuted, the ARTIFEX pause remains, and no arm-B/canary claim exists. Threshold, unit, scope,
admission states, arms and expected branches were not changed after observation.

## Attempt v1.1.2 — owner-authorized bounded successor

Frozen contract SHA-256: `182c03c75b919905a47d5f86ba19f8034e4b11b9db6fbac0c0cf690a36a0c754`.
Frozen manifest SHA-256: `b759ad744669340facc262d7f6e9df02c51bf74c44c34546133def4a5c6ea984`.
Threshold, qualified unit, five-slot scope, admission reducer, arms, anti-displacement predicates,
measurement implementation and exact canary branches are unchanged from v1.1.1. D158 disclosed
the only interventions: thirteen ready bundles materialized, invalid bundle declarations made
explicit, and terminal P6.2/P6.5/P6.6 historical inputs narrowed to exact facts/digests without
removing an item, slot, deliverable or terminal evidence.

### Arm A — migrated plan

Raw: `artifacts/P6/acceptance-arm-a-migrated-v1.1.2.json`, SHA-256
`6a0b56d2c0fdcd49a2e7a4040df74c2c459e6720063f4b0f1025cd0f85074e0b`.

| Metric | Observed | Frozen condition | Result |
|:--|--:|:--|:--|
| admission coverage | historical 17 · pending 0 · ready 30 | report separately | PASS |
| ready failures | 0/30 | 0 | PASS |
| maximum item weight | 89,015 | ≤100,000 | PASS |
| ready gaps / oversized inputs | 0 / 0 | 0 / 0 | PASS |
| historical gaps | 17 missing pre-v2 carriers | evidence-only | OBSERVED |

The D2 reducer for arm A is `pass`; full ready coverage is 30/30. The anti-displacement answer is
`no`: all 47 items and five executor slots remain traversed, current ready work was neither split
nor deferred, and the terminal capsule retains source-set digests plus load-bearing facts.

### Integrity failure, downstream stages and final verdict

The mandatory decision projection immediately preceding raw capture failed because D157's filename
contained an invalid dot slug and its reciprocal supersession metadata was incomplete. The
non-fail-fast shell continued and captured the D2-positive raw. Renaming/correcting D157 after
observation changes a selected P6.9 bundle input; rerunning would violate the one-shot D158
change-control rule. Details are in
`findings/P6.9-v1.1.2-terminal-integrity-failure-2026-08-09.md`.

Therefore overall attempt v1.1.2 is **`fail`**. Arm B and session canary are **NOT-RUN**; no claim
is made for either. ARTIFEX remains paused. P6.9 closes `Done with deviations`, and D158 forbids a
new successor/design-loop from this plan.
