---
id: D77
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

D77 supersedes D76's use of the write-heavy P3.4 plan item as the no-write smoke manifest source, while preserving D74's live-provider objective and frozen `slice-manifest-v1`. P1.6 now freezes exact provider-specific `dispatch-task-manifest-v1` smoke task/grant carriers whose task hashes, empty write/tool allowlists and temporary-repo boundary are distinct from P3.4; P2.6 alone materializes per-provider manifest→grant→replay→admission instances and an immutable index; P3.4 only implements the parent activity seam and executes those admitted child tasks. **Consequences:** P1.6/P2.6/P3.4 gain explicit task-set/index files and two provider-specific instances, while the P3.4 Task Contract/item hash is forbidden as smoke authority and every grant-as-admission or plan-item-as-smoke substitution refuses before intent. RAG:— (repo-grounded: `brief/10-post-d76-audit-remediation.md`; latest Audit design F1; `research/23-post-d76-audit-remediation-reconcile.md`; frozen `root/contracts/slice-manifest-v1.md`).

## Почему

One carrier can no longer mean both candidate implementation writes and a read-only readiness probe; separate child task identities keep no-write scope honest without rewriting a frozen plan-item compiler contract.
