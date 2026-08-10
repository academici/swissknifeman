---
id: D48
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Every F18-listed Validation uses exact worktree-local root or package-cwd invocations. `roadmap.md` carries the closed P4.4/P4.6 cwd→command matrix; P5.1–P5.4, P6.1/P6.3 and P7.1/P7.4 name helper path, subcommand, frozen manifest/action/evidence/contract inputs, output carrier and exact plan-lint invocation. Prose aliases such as “targeted tests”, “owning check”, “verify-results”, “Helper --write/--check” or “rerun green” are not acceptance commands. RAG:— (repo-grounded: audit F18 and affected phase `Files`/Validation).

## Почему

Cold-start executors and the final auditor can reproduce the same gate byte-for-byte; broader full-suite commands are accepted where a package has no narrower stable public runner.
