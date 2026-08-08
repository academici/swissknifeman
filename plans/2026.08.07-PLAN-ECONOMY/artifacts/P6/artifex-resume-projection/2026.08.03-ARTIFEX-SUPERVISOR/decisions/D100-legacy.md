---
id: D100
date: 2026-08-05
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

D100 supersedes D79 only for P4.6's frozen post-repair status literal: the worktree-local Harness CLI's exact clean/noop result is `Статус: green`, not `Статус: ok`. The one-repair limit, exact target/provider/flags, two-action preflight, zero residual actions, independent validator, and P4.4's independent recheck remain unchanged. **Consequences:** P4.6 resumes from its already-applied single repair and must emit evidence/validator accepting only literal `green`; a second repair is forbidden. RAG:— (repo-grounded: `findings/P4-hook-integrity.md`; `packages/harness/lib/harness/hooks.py`; P4.6 observed command output).

## Почему

The acceptance now verifies the current owner surface literally rather than treating a clean result as a defect; all fail-closed action/target/ownership checks remain intact.
