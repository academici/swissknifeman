---
id: D88
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

D85's mandatory package outcome is promoted earlier: after P3.5–P3.7 are GREEN, P3.8 consumes D86 and creates the standalone `packages/artifex/` runtime/CLI/tests as the sole live implementation. P4 and P5 must import and execute package paths only. P6 no longer migrates runtime code: P6.1 freezes the remaining D87/root/installer/doctor/docs/operations scope, P6.2 integrates those public surfaces, P6.3 completes operations/docs, and P6.4 audits the finished product. D2/D57 are superseded only for this timing/ownership transition; frozen P1/P2 carriers, P3.1–P3.3 history, P3.4 forward fixes, P5 evidence thresholds and D85–D87 authority remain unchanged. **Consequences:** P3 grows to 8 items, the plan grows to 39 items, P3 cannot close before package promotion, and no later assurance may certify plan-local runtime bytes as the shipping implementation. RAG:— (owner-grounded: `brief/14-owner-finished-product-guarantee.md`; repo-grounded: package/single-SSOT canons and `research/27-finished-product-outcome-reconcile.md`).

## Почему

Testing a prototype and later shipping a migration would leave the user without a guarantee that the tested code is the delivered package; moving the boundary before P4/P5 makes assurance and pilots product-representative.
