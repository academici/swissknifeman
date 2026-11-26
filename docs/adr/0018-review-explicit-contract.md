# ADR 0018: Review is an explicit, mandatory contract

Status: proposed
Date: 2026-10-25

## Context
Legacy items allowed review modes `none|self|requested`; "no field" silently meant no review.

## Decision
Every unit/item in a revision has an explicit `review` requirement: `required` (profile, independence, max_rounds,
required evidence), `self`, or `waived` with `reason` and `waived_by`. Missing review is a validation error. A
review counts only for the output it was performed on; `attention` requires deviation acceptances; repair never lowers
severity. Findings have a stable `finding_key` across rounds; fix briefs are built deterministically from triaged findings.

## Alternatives considered
- Review optional by default: rejected (evidence over claims).

## Consequences
Legacy `none` imports as `waived(reason="legacy: none")`, flagged as imported.

## Compatibility
Legacy `GREEN|ATTENTION|RED` verdicts map to `green|attention|red`.

## Verification
Acceptance invariant tests are in [`tests/unit/execution/domain/test_acceptance.py`](../../tests/unit/execution/domain/test_acceptance.py).

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

E26 makes TaskAccepted terminal only after integration and required rechecks. E03 distinguishes manual repository validation/review records from product review invariants; E58 defines bootstrap campaign review policy.

## D2 review fixes and commit attribution

An `agent_review` stage can set `params.reviewer_with_fix = true` for a writable task.
Pair it with a reviewer profile whose policy permits writes inside the task's granted worktree scope,
and include a task-scoped `run_checks` stage in the workflow. The stage uses the reviewer role and
review result contract. Gate and standalone range reviews use read-only review. Reserve the last
configured review round for read-only verification.

The stage records its verdict and findings against the immutable output it opened. If its publishable
worktree tree changed, it seals a new output attributed to the reviewer step. The workflow runs task
checks against the new output and requires a fresh read-only review after successful checks. Findings
continue to use their stable keys. The fix pass's verdict supplies no clearance for the new output.

`execution.integration.commit_mode = "per_stage_attributed"` works with `rebase` and `merge`. It publishes
one commit for each sealed stage output that changes the target tree, in output sequence order, and keeps
the full chain in the effect receipt. `final_only` publishes the accepted tree with that output's identity
and repeats the attribution of its contributing steps in sequence. `implementation_and_fixes` continues
to publish every sealed output.

Commit messages carry server-owned SKM identities, the output sequence number and, when linked to a
completed review, that review's ID and round. Each `SKM-Findings` value is a stable finding key from
the review or fix brief. Revision-backed task references identify the immutable revision and entity by
ID and carry a SHA-256 digest of the canonical task entity. Ad hoc references identify the inline
specification file version and carry its content digest. Generated work tasks reference their task ID
and carry a digest of the task kind, origin, and declared write scope. Task specification text, artifact
paths, and finding text stay in their source records.

`Plan` and `Plan-Ref` identify the plan alias and task key. `Plan-Role` and `Plan-Actor` identify the role
and assigned route. `Executed-By` and `Executor-Session` describe the output producer. `Reviewed-By`
and `Reviewer-Session` describe the linked reviewer. Actual runtime attribution comes from a matched
runtime observation, and session trailers require an opaque session identifier. Unavailable evidence
is omitted. The trailer formatter preserves order and repeated values.

Run `make check-trailers TRAILER_REV=BASE..TIP` to check published integration commits for trailer
structure, identity, review, attribution and task-spec reference invariants. Git trailer checks
validate the message structure. The worker and server verify the underlying execution evidence.
