---
id: D2
date: 2026-08-14
status: accepted
item: P1.1
items: [P1.1]
supersedes: []
superseded_by: null
---
## Решение

`review_policy.phase_audit_subject()` остаётся SSOT `phase-audit-subject/v1`.
Все consumers нормализуются через него; new phase-audit writer персистирует
только `Pn`, а raw historical rows не переписываются.

## Почему

Новый subject field/schema создал бы второй носитель identity. Текущий normalizer уже
используется delivery/lint/journal, поэтому узкая parity-fix дешевле и безопаснее.

**Evidence:** RAG:— (`findings/01-subject-and-policy-recon.md`, `findings/03-p1-recovery-recon.md`).
**Actor:** design/gpt-5.6-sol/high.

## Consequences

`plan_gates` и `task_contract` получают missing normalization; writer canonicalizes before
idempotency/persistence; design audit subject не изменяется.
