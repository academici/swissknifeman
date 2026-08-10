---
id: D70
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P2.4 maps the frozen P2.3 OWNER reason `RETRY_BUDGET_EXHAUSTED` at `READY` to the existing frozen run transition `budget_exhausted → BUDGET_EXHAUSTED`; the journal row keeps the triggering slice/attempt/idempotency identity and the exact closed authority decision as minimized evidence, while no intent or activity is allowed. `BUDGET_EXHAUSTED` is the v1 global admission breaker: every slice stays stopped until explicit `owner_decision_continue` or `owner_decision_abort`. No P1 state/event/reason/version/hash changes are authorized. Rejected alternatives: a new breaker event/state, relabelling as source drift/incident, a derived-only flag, or continuing other slices under a per-slice-only stop; details in `research/16-p2.4-circuit-breaker-reconciliation.md`. RAG:— (repo-grounded: `findings/14-p2.4-circuit-breaker-recon-2026-08-04.md`; `research/16-p2.4-circuit-breaker-reconciliation.md`; frozen `authority-policy-v1` and `supervisor-run-v1` carriers).

## Почему

Repeated-finding exhaustion is already a retry-budget boundary and the run contract already has its durable stop transition; composing those owners closes the gap without a major frozen-contract ripple or an implementation-local default.
