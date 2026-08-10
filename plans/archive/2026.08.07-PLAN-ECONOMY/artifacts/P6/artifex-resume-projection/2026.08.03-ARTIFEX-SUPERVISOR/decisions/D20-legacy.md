---
id: D20
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Наблюдённый `harness.codex.lifecycle` stale-source hook state фиксируется как preflight defect и блокирует утверждение fully-green runtime baseline, но не чинится этим design item. RAG:— (repo observation 2026-08-03).

## Почему

План не присваивает чужую dirty-tree remediation и не выдаёт warning за green.
