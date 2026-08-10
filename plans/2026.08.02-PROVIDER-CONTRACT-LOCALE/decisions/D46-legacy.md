---
id: D46
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P0.4 evidenced no-op is a deterministic Validation result, never an owner gate: it requires the frozen checker to pass over committed P0.1 classification plus fresh independent detector/provider-trust evidence with `action_set=[]`, zero plaintext-secret findings and zero protected-target delta. Only a non-empty mutation branch requires the exact containment D#. RAG:— (repo-grounded: P0.3/P0.4 Validation and `roadmap.md` deterministic note).

## Почему

Avoids asking the owner to authorize no mutation or letting an executor treat no-op as a waivable approval branch; security writes remain fail-closed.
