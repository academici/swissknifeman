---
id: D27
date: 2026-08-02
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P5 expands to four sequential full-review manual items: freeze exact no-write manifest/Owner D# → preserve/register overrides → non-destructive managed repair → owner-gated quarantine plus two-run convergence. A plan-local runner sequences only terminal P3/P4 public APIs and may not encode provider semantics. RAG:— (repo-grounded: P3.2/P3.3 boundaries and `research/05-p5-consumer-migration-design.md`).

## Почему

Direct `skiller update --all`, generic `maind sync --all` or ad-hoc per-project commands lack the sealed exact-set action/rollback carrier; the four-way split keeps authority and rollback auditable.
