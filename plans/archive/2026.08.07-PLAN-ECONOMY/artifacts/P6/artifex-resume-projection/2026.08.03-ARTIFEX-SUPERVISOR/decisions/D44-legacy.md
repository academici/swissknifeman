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

A write-capable attempt uses a detached identity-locked linked worktree at a pinned base; stable inventory comes from `git worktree list --porcelain -z`, and `--force`/broad prune are forbidden. RAG:✅ 2026-08-03 current official Git worktree semantics in `findings/08-p4-recovery-security-recon-2026-08-03.md`.

## Почему

Git documents separate working/index state but shared repository state; exact ownership is required before cleanup or integration.
