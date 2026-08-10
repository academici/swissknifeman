---
id: D7
date: 2026-08-07
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Все семь фаз запечатаны contract-first: каждая несёт блок «Потребляет / Производит / Границы», детали items — just-in-time при `plan-design <ID> Pn`.

## Почему

Фазы слабо связаны и утверждаются владельцем поштучно; проектировать семь фаз одним потоком — смешанные согласования и ошибки. Порядок фаз при этом ВЫВЕДЕН, а не выбран (`research/01-…` §8). RAG:— (repo-grounded: `research/01-target-architecture.md` §8)
