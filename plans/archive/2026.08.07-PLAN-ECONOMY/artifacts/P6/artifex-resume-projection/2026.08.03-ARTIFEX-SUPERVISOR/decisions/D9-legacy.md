---
id: D9
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Prototype state — hash-chained append-only JSONL + derived atomic snapshot + exclusive writer lock; SQLite/Temporal не являются runtime dependencies. RAG:✅ SQLite WAL and Temporal recovery principles; adapted to stdlib.

## Почему

JSONL прозрачен, переносим и не зависит от host SQLite WAL/version semantics.
