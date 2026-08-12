---
id: D14
date: 2026-08-12
status: accepted
item: P1.2
items: [P1.2, P1.3]
supersedes: []
superseded_by: null
---
## Решение

P1.2 объявляет exact predecessor output
`artifacts/P1/layout-migration-ledger-v1.json` в `Deliverables`. Эта же ссылка уже
зафиксирована в `Files` P1.2 и `Required Reads` P1.3; точная декларация делает
consumer admission однозначным до материализации ledger. RAG:— (repo-grounded:
`packages/task/lib/task/plan_admission.py`, `phases/P1/P1.2.md`, `phases/P1/P1.3.md`).

## Почему

Без exact deliverable path P1.3 классифицируется как ready с отсутствующим input вместо
`pending-producer`, что создаёт невыполнимый bundle gate между adjacent items. Правка
не меняет scope, format или semantics ledger. RAG:— (repo-grounded:
`packages/task/tests/test_plan_gates.py`, `packages/task/tests/test_plan_admission.py`).
