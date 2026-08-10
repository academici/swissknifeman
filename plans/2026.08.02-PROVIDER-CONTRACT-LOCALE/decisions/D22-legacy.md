---
id: D22
date: 2026-08-02
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Locale runtime lives in a shared stdlib-only `core/locale` domain and consumes already-read P3 descriptors; packages own their catalogs/targets and both providers receive the same immutable per-surface context. RAG:— (repo-grounded: shared-core/provider-parity rules, P2/P3 phase boundaries and `research/04-p4-locale-migration-implementation-design.md`).

## Почему

Alternatives were provider-local locale state or duplicated package resolvers; both would make fallback/provenance diverge and let an adapter become canonical intent.
