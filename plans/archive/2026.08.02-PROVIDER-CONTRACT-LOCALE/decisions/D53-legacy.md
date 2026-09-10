---
id: D53
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P5.1 `plan` is no-write only with respect to consumer/provider targets and may atomically create exactly the named manifest and initial journal; `check` changes no byte anywhere. Validation records separate byte-delta assertions for the two subcommands and rejects any other initialization output. RAG:— (repo-grounded: audit F24 and P5.1 Files/Validation).

## Почему

Removes the literal contradiction while retaining a fail-closed target boundary and deterministic initialization carrier.
