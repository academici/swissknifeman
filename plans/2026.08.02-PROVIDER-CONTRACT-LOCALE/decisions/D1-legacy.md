---
id: D1
date: 2026-08-02
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Use a versioned provider-neutral desired-state contract plus adapter-owned observed status; no adapter writes canonical intent. RAG:✅ 2026-08-02 control-plane query.

## Почему

Separates user selection from provider quirks; see `research/01-target-architecture.md`.
