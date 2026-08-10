---
id: D3
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Supervisor scheduler/arbiter/recovery path детерминирован; LLM calls являются activities за side-effect boundary и не принимают state-transition решения. RAG:✅ Temporal workflow/activity patterns; adapted without dependency.

## Почему

Replay должен давать тот же переход без повторного модельного суждения.
