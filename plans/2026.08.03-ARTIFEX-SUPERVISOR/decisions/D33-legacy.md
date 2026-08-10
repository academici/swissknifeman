---
id: D33
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P2 run storage uses strict canonical hash-chain JSONL, a POSIX advisory single-writer lock and derived atomic snapshots; locking, name replacement and durability are separate evidence claims, and unsupported directory durability stays explicit. RAG:✅ Python 3.12 official API boundaries in `findings/06-p2-runtime-recon-2026-08-03.md`.

## Почему

Tolerant analytics readers and non-fsync `core.io` writes cannot be reused for a recovery authority; product portability/physical durability remains P4/P6 evidence.
