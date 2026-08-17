---
id: D91
date: 2026-08-17
status: accepted
item: P7
items: [P7, P7.1, P7.2, P7.3, P7.4, P7.5, P7.6, P7.7]
supersedes: []
superseded_by: null
---
## Решение

`phase-close: terminal-blocked-deviations`

Close P7 as `🟠 Done with deviations` after its terminal recovery-close. This is a phase-scoped
recording exception only: P7.4 and P7.7 remain `🔴 Blocked`, their RED audit and
`BLOCK_CONFIRMED` evidence remain append-only, and D89 retains `release_authorized=false`.

## Почему

P7.7's committed continuation prescribes recovery-close P7.7 followed by phase close, but the
former phase gate treated those preserved terminal blocked items as a permanent prohibition. The
phase has no remaining executable in-scope recovery. Recording the completed non-releasable phase
truthfully is preferable to inventing another audit, live-provider retry, or release operation.

## Consequences

This decision authorizes neither a release exception nor a retry. Tag, push, publish, live-provider
retry, fleet/Brain mutation, and consumer repair remain unauthorized. D89 is neither superseded nor
weakened; release remains unauthorized while its blocker set is non-empty.
