---
id: D26
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P0 исполняется последовательно без Workflow: P0.2 зависит от baseline/reuse границ P0.1, P0.4 — от authority/provider evidence, P0.5 — от P0.1–P0.4; все items имеют `Exec = manual`. RAG:— (repo-grounded: `research/06-p0-evidence-freeze-design.md`; plan-protocol orchestration criterion).

## Почему

Фаза не имеет трёх независимых plan-exec slices и не является автономной внешней цепочкой; orchestration carrier здесь создаст лишний контекст и второй scheduler.
