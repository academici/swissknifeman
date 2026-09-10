---
id: D88
date: 2026-08-16
status: accepted
item: P7.1
items: [P7.1, P7.2, P7.3, P7.4]
supersedes: []
superseded_by: null
---
## Решение

P7 is a package-contract delivery boundary, not authorization to operate the external P5/P6
fleet.  P6's exact health evidence stays intact, but its non-green project rows and the
unapproved P5 rollout are deferred operational work and are not P7.1 package blockers.

Claude Code is accepted in P7 as a documented additive projection.  It is explicitly
`not-live-verified`: P7 neither retries the unavailable subscription nor infers behavioral
success from documentation.  The existing D87 replay is retained as privacy-minimized diagnostic
evidence only.  Codex replay/ablation observations are likewise not a release-efficacy gate;
they may inform a later field-feedback item but do not change the frozen shared contract.

P7.1 validates source/projection admission, deterministic evidence structure, P5 producer
integrity, provider-manifest coverage, and privacy.  Its result is `Done with deviations`, with
the explicit deferred operational and live-efficacy boundary recorded in the evidence bundle.

## Почему

The repository package can be delivered and documented without claiming that a disabled external
subscription passed a live evaluation or that 23 consumer projects have already been rolled out.
Keeping those facts as blockers of their own operations, rather than retrying them inside P7.1,
preserves evidence integrity and prevents an unrelated fleet operation from stalling package work.

## Consequences

D87's 54-row carrier remains an exact diagnostic denominator and is never rewritten as a passing
provider evaluation.  A future live-efficacy or fleet-release decision must reopen a new scoped
item with working provider access and explicit rollout authority.  P7 does not tag, publish, or
declare the external fleet healthy.
