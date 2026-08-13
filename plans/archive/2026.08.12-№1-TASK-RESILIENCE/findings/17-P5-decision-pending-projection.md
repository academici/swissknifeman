# P5 decision-pending projection repair — 2026-08-13

## Signal

The P5.3 scope-change request was durable and unresolved, but
`task.plan_requests._transition_result()` mapped both `pending` and
`pending-authorization` to `blocked`. Journal line 197 therefore replaced the honest
`closed-deviations` position with a terminal block even though no owner outcome existed.
RAG:— (repo-grounded: `journal.jsonl`, `packages/task/lib/task/plan_requests.py`,
DecisionRequest `P5.3-files-boundary-2026-08-13`).

## Repair

Commit `008430d6` maps unresolved semantic outcomes to the observation
`decision-pending`; apply still resumes `in-progress`, while park/reject/escalate remain
terminal `blocked`. Focused request/item-state/review-policy suites passed 102 tests and
Task validation passed 873 tests with one skip. An exact replay of the existing request
appended journal line 199 and restored P5.3 to its live audit attempt without duplicating
the queue request.

## Prevention

The request, return-loop, projection-failure and pending-authorization tests now assert
that unresolved owner input preserves the prior execution position. This is a
PROMOTE-CANDIDATE for the plan-protocol anti-pattern catalogue: a durable question is an
observation, not a terminal execution result.
