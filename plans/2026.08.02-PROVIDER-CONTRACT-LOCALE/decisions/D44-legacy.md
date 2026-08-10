---
id: D44
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

D39's per-cwd rule explicitly includes P4.2 and P4.3: the root coordinator alone owns `configs/locale-corpus-v1.json`, plan evidence, integration and closure, while a fresh `codex -C packages/skiller` session owns only the exact Skiller paths and package validation commands enumerated in P4/roadmap. RAG:— (repo-grounded: root/package `AGENTS.md`, P4.2/P4.3 Files/Validation and `roadmap.md` exact slice rows).

## Почему

Removes the remaining root-session write path into `packages/skiller/**` without adding item IDs or splitting shared-ledger authority.
