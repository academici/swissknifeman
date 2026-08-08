---
id: D45
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Linked worktrees prove file/index write-lane isolation only, not security. Integration is one exclusive clean exact-base lane using the validated attempt commit; conflict aborts to verified preimage or enters OWNER, with no automatic resolution or owner-dirty-tree mutation. RAG:— (repo-grounded: D8/D18 and `research/10-p4-assurance-design.md`).

## Почему

Avoids promoting a Git convenience into credential/process authority and prevents conflict resolution from changing the acceptance contract.
