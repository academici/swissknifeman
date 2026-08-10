---
id: D22
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Failure acceptance включает crash после каждого durable append/public boundary, duplicate delivery, orphan worker, timeout/quota/approval failure, corrupted/truncated/reordered journal, plan/source drift, budget exhaustion and merge conflict outside assigned scope. RAG:✅ 2026-08-03 Superset Automations first-party delivery-semantics recheck + internal synthesized failure model → `findings/02-reference-products-2026-08-03.md`.

## Почему

Happy-path pilot не доказывает supervisor reliability.
