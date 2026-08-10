---
id: D11
date: 2026-08-02
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P0 pre-mortem: likely failure modes are partial fleet coverage, dirty-tree state reported as shipped, secret leakage into evidence, ownership inferred from names, provider success masking the other provider, and mutation outside the approved target. RAG:— (repo-grounded: brief, current dirty tree, predecessor P0/P7 findings).

## Почему

Mitigations are assigned respectively to P0.1 coverage/hash gates, HEAD/worktree separation, redaction self-tests, P0.2 evidence classes, per-provider rows, and P0.3/P0.4 protected-delta/rollback gates.
