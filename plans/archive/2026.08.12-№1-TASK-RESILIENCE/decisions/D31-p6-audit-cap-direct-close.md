---
id: D31
date: 2026-08-13
status: accepted
item: P6.2
items: [P6.1, P6.2, P6.3, P6.4]
supersedes: [D30]
superseded_by: null
---

## Решение

AUDIT-CAP: третьего Audit P6 нет; фаза закрывается штатным `task:plan-close`.

Владелец разрешает direct-close P6 после terminal P6.2: exact `v0.13.2`
candidate уже прошёл полную matrix, новый local annotated tag создан, а D30 не
расширяется на новый audit или release attempt.

## Почему

`phase_audit_policy` правильно требует fresh audit для `P6.1` со статусом
`🟠 Done with deviations`, но это был бы запрещённый третий Audit P6. D31 —
узкий owner override существующего close gate, а не ослабление validation или
пересмотр historical evidence.

## Consequences

`task:plan-close` сверяет текущий phase candidate и D31 перед закрытием. P6.1–P6.4
не переисполняются; `v0.13.0`, `v0.13.1`, `v0.13.2`, push, GitHub release и
registered-project rollout не изменяются.
