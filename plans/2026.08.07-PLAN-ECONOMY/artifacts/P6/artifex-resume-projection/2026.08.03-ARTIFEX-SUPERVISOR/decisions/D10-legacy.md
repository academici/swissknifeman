---
id: D10
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Каждая side-effect boundary использует `intent → fsync/reopen/verify → call → observation → fsync/reopen/verify → acceptance`; intent несёт stable run/slice/attempt/idempotency key и source/input hashes. RAG:— (reliability design adapted from durable execution patterns and current P5/P6 WAL precedent).

## Почему

Crash не должен превращать неизвестный side effect в молчаливый повтор.
