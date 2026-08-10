---
id: D43
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P4.2 repairs only existing P2/P3 store/scheduler/worker/CLI owners; unresolved intent is observed before action and may become exact-post accept, exact-pre retry-with-budget, recognized-partial whole-slice rollback or third-state OWNER—never blind rerun. RAG:— (repo-grounded: D10–D11, `research/10-p4-assurance-design.md`).

## Почему

Preserves one state machine and makes duplicate external calls machine-observable through stable idempotency keys/counters.
