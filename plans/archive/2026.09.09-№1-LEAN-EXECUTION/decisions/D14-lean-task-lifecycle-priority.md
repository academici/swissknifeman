---
id: D14
date: 2026-09-10
status: accepted
item: P7.1
items: [P3.1, P3.2, P3.3, P3.4, P6.1, P6.2, P6.3, P6.4, P7.1]
supersedes: [D3, D8, D11, D13]
superseded_by: null
---
# D14 — Consolidate the lean Task lifecycle before P3

**Actor:** owner + design-author/gpt-5.6-sol/high
**Evidence:** RAG:— `brief/01-refinements.md` owner priority correction; `findings/15-lean-lifecycle-overhead-2026-09-10.md`; `findings/16-p7-design-preflight-2026-09-10.md`; `research/08-p7-lean-control-loop.md`

## Решение

Execute P7.1 immediately after P2 and before P3 as one vertical consolidation of the normal Task
lifecycle: compact admission, implementation, changed-scope validation, one terminal projection
pass, one scoped commit by default and one semantic continuation. Existing runtime owners remain
authoritative; P7 may add one transient orchestration API only when it removes more command/canon
logic than it adds and creates no new persisted schema, carrier, status, review kind or parallel
`lean` mode.

Retire unstarted P3.3 and P6.1–P6.4 from the executable plan. P7 owns normal-path validation
selection and prompt/canon reduction; P3.1/P3.2/P3.4 remain only for the distinct impact, routing
and evidence-topology seams. The historical execution admitted by D13 stays historical evidence,
but its narrow future P7 contract is replaced by this decision.

## Почему

The P2 audit proved that full package/fleet replay, cross-plan failure coupling, unconditional
projection work, mandatory two-commit bookkeeping and audit-as-executor dominate the observed
cycle. A parallel fast path would preserve both paths and increase policy size; the P3.3 receipt
programme and P6 evaluation harness would add machinery before the measured normal path is made
cheap. One deletion-led consolidation is the smallest owner-visible correction.

## Consequences

**Consequences:** D3 and D11 no longer authorize the P6 experiment; D8's separate validation-
receipt owner is replaced by P7's transient change-impact selection while its remaining P3 seams
are retained; D13's historical direct execution remains true but its narrow permanent-fix scope is
superseded. P3.3 and the P6 phase carriers/routing are removed, P3.4 consumes the completed P7.1
contract, and roadmap/handoff point to P7.1 before P3. Rollback is the single plan/product commit
plus regeneration through existing owners; security/authentication, destructive migration,
irreversible external action, payment/accounting, concurrency/shared-state, public API/schema and
low-confidence impact boundaries continue to widen and fail closed.
