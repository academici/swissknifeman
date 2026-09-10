---
id: D36
date: 2026-08-02
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P7 is four sequential manual/full-review items: exact acceptance → permanent regressions → operations/release candidate → cold frontier/xhigh audit. It declares no workflow and performs no tag, push, publish, fleet/Brain repair or destructive cleanup. RAG:— (repo-grounded: P7 Inputs/Deliverables and plan-protocol orchestration criterion).

## Почему

Every item consumes the prior committed evidence, so parallel fan-out would either race a moving acceptance set or let the audit inherit implementer assumptions.
