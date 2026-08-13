---
id: D27
date: 2026-08-13
status: accepted
item: P6.2
items: [P6.2]
supersedes: []
superseded_by: null
---
## Решение

Выбран owner-option `repair-and-patch-release`: P6.2 реопенится как один recovery item,
делает phase-candidate fingerprint детерминированным по Git tracked set, повторяет
полные release gates и создаёт новый локальный annotated patch tag `v0.13.1`. `v0.13.0`
не удаляется, не перезаписывается и не двигается; P6.3/P6.4 evidence не
переписывается. Push/GitHub release остаются неавторизованными. RAG:—
(owner-grounded: `decisions/queue.jsonl`; repo-grounded: `findings/22-P6-audit-2026-08-13.md`,
`research/09-P6.2-tracked-tree-patch-release-design.md`).

## Почему

Простая замена wildcard на directory привяжет fingerprint к игнорируемым runtime
байтам, а сохранение текущей семантики оставит stale-audit дыру. Git tracked set
даёт воспроизводимую membership boundary, а patch release честно отделяет
исправление от уже созданного и раскатанного `v0.13.0`. RAG:—
(repo-grounded: `packages/task/lib/task/plan_gates.py`, release-discipline).

## Consequences

Исторический `v0.13.0` сохраняет зафиксированный audit finding; GREEN доказывается
только для нового `v0.13.1`. P6.2 получает новый lifecycle episode в append-only journal;
прежние terminal events и release capsules остаются history, а не подменяются.
