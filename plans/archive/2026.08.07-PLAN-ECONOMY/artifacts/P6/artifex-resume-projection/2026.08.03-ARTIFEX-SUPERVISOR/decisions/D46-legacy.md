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

P4.4 consolidates candidate path/env/content checks, while an independent validator scans actual evidence bytes through public Task `bundle_lint` plus closed P1/P3 schemas. Full security readiness additionally requires the effective hook dry-run itself GREEN; the current `stale-source` warning blocks it and is not repaired in P4. RAG:— (repo-grounded: `findings/08-p4-recovery-security-recon-2026-08-03.md`; `packages/task/lib/task/task_contract.py`).

## Почему

Candidate declarations and exit zero cannot self-certify privacy or mask environment drift.
