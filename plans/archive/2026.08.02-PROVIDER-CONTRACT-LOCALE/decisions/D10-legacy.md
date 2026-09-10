---
id: D10
date: 2026-08-02
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Recovery-gate approval and live security containment are separate items P0.3/P0.4; P0.4 is a no-op when fresh evidence finds no active exposure, and otherwise requires an exact owner D# before any external write/revocation. RAG:— (repo-grounded: root security/worktree rules and predecessor gate pattern).

## Почему

A design item cannot self-authorize an irreversible provider action; separation keeps approval, rollback and evidence auditable.
