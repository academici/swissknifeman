---
id: D79
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

D79 supersedes the roadmap's direct P4.3→P4.4 edge. New P4.6 is the sole owner of one worktree-local effective Codex hook `--repair`, the exact post-repair `--dry-run`, minimized evidence and an independent validator; execution order is P4.3→P4.6→P4.4. P4.4 still reruns the effective command and refuses `warning`, `stale-source` or `→ update`; doctor/syntax/exit 0 never substitute. **Consequences:** the plan grows from 34 to 35 items and performs one explicit trusted-state repair before security assurance; the current design session does not repair hooks, package sources remain outside P4.6 Files, and P4.4 cannot start unless P4.6 is terminal GREEN. RAG:— (repo-grounded: `findings/hooks-stale-source-precondition-2026-08-04.md`; latest Audit design F3; `research/23-post-d76-audit-remediation-reconcile.md`).

## Почему

The known reproducible prerequisite warning now has a named producer/evidence carrier instead of becoming a predictable late P4 refusal or a false GREEN inferred from exit status.
