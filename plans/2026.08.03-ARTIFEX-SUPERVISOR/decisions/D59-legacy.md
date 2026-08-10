---
id: D59
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Run-state compatibility uses validate → separate copy/backup → new-reader proof → rollback/downgrade postimage; uninstall never deletes run history, and the kill switch blocks new starts while preserving inspect/resume/reconcile/rollback. RAG:— (repo-grounded: P1 run contract, P4 recovery design and worktree-safety canon).

## Почему

In-place migration or a total kill switch can strand the durable evidence needed to recover.
