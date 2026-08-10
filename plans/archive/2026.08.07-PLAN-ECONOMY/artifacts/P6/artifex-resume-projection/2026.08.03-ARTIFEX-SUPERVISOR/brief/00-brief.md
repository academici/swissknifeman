# Owner brief — reliable Artifex supervisor

**Captured:** 2026-08-03
**Source:** direct owner conversation; this file preserves intent, not implementation instructions.

## Problem

The owner does not want to run a large phase through a conventional Workflow because the
coordinator/subagent exchange can cause severe token overuse. The desired system is a dedicated
long-running supervisor which drives subphases/slices, launches workers, evaluates their results,
handles routine conflicts and persists progress without requiring the owner to approve the same
recommendation every few minutes.

## Desired operating model

- The owner states canons, boundaries and forbidden areas once at the beginning of a run.
- Approximately 99% of routine recommendations are expected to be acceptable, but this is an
  owner hypothesis to measure, not an acceptance result to assume.
- Inside those canons the supervisor may choose and apply the lowest-risk legal option.
- Genuine canon changes, destructive/external/security actions and unknown states still go to the owner.
- Routine owner questions are bundled; the owner primarily sees final results, residual deviations
  and a compact set of true decisions.
- Long tasks are split into re-definable slices; a resumed run must continue from durable evidence,
  not from the memory of one chat session.
- Token economy matters as a first-class acceptance dimension, alongside correctness and recovery.

## Requested evidence base

The new plan must build on:

1. archived `2026.07.18-FOREMAN` and its Artifex decisions/contracts;
2. the HARNESS-AGNOSTIC absorption/rescope verdict;
3. `roadmap/artifex-thin-wrapper.md` and its activation criteria;
4. current repository/Harness/Task capabilities rather than archived assumptions;
5. fresh official research into current Codex/Claude subagent and long-horizon behavior;
6. a pattern review of <https://github.com/RunMaestro/Maestro> and
   <https://github.com/superset-sh/superset>.

## Explicit non-goals for this authoring pass

- No implementation of Artifex or package creation.
- No execution of supervisor plan items.
- No modification of provider/fleet/Brain/generated/release state.
- No rewriting of FOREMAN, AGENT-RELIABILITY or HARNESS-AGNOSTIC archives.
- No change to item statuses or remediation content in the paused provider plan.
