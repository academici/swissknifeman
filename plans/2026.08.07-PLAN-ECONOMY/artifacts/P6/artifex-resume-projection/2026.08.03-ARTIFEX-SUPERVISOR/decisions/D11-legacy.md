---
id: D11
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Resume/reconcile принимает только exact approved postimage, exact preimage либо контрактно распознанный partial с whole-slice rollback; third state, torn/reordered chain, source drift или missing backup отказывают. RAG:— (repo-grounded P6 WAL precedent; external durable-execution synthesis).

## Почему

Восстановление не угадывает состояние.
