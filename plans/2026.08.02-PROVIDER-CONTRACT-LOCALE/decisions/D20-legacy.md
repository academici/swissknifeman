---
id: D20
date: 2026-08-02
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P3 composes the existing `core/provider` configuration, manifest, registry and artifact-lock primitives into a control-plane resolver and adapter boundary; it does not duplicate their identities, precedence, capability levels, lock semantics or provider projections. RAG:— (repo-grounded: `core/provider/{config,manifest,registry,artifact,lock}.py`, `research/03-p3-control-plane-implementation-design.md`).

## Почему

A new monolithic store or package-local resolver would become a rival source of truth and break the predecessor's independent-adapter contract.
