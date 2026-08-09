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
