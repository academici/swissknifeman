---
id: D23
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Живой `harness run` становится отдельной baseline/reuse lane P0.1 наряду с manual и Workflow; P1/P2 обязаны предъявить gap crosswalk перед повторением его queue/worker/gate/journal семантики. RAG:— (repo-grounded: `packages/harness/docs/reference/exec-wave.md`; `findings/04-p0-design-verification-2026-08-03.md`).

## Почему

Bootstrap верно отрицал durable supervisor, но пропустил уже существующий последовательный exec-wave driver; игнорировать его означало бы проектировать дубликат.
