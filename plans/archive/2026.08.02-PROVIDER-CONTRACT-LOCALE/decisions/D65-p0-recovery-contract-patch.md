---
id: D65
date: 2026-08-10
status: accepted
item: P0.6
items: [P0.6]
supersedes: []
superseded_by: null
---
## Решение

P0.6 owns one compatible corrective successor to `provider-recovery-gates-v1.md`: semantic
validation of every gate column, exact preservation of G01–G11, and an acyclic phase-local
independent-verifier topology. Recommended version is v1.0.1, but the bytes remain draft until a
new exact typed `contract_freeze_decision` accepts the produced diff; D63 cannot be reused. P7.4
remains the final release audit, not the verifier that gates entry into P1–P7. RAG:—
(repo-grounded: audit F3/F5, D63 and `research/11-p0-audit-reopen-design.md`).

## Почему

The intended no-write/recovery semantics are already frozen, but their current checker and
transition topology fail open; separating corrective implementation from the new freeze authority
prevents self-approval.
