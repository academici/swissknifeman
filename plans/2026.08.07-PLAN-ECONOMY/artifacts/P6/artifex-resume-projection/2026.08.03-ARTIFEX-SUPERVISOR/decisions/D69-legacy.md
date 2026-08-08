---
id: D69
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Reopen P2.1 only for terminal-stable test isolation: deterministic compiler tests use an item-owned literal pending P2.1 S3 fixture, while a separate live Harness boundary test requires closed P2.1 to be absent from runnable `items` and present in `excluded_terminal`. Borrowing any sibling item's live row, admitting terminal rows to production compilation, or changing Harness/Task is forbidden. P2.2 stays terminal and the uncommitted P2.3 scope is preserved. RAG:— (repo-grounded: `findings/13-p2.1-terminal-fixture-recon-2026-08-04.md`; `research/15-p2.1-terminal-fixture-remediation.md`).

## Почему

The previous fixture merely shifted lifecycle dependence from P2.1 to P2.2 and failed when P2.2 closed; separating immutable conformance input from the live terminal-exclusion contract makes the predecessor test stable for all later phases without weakening production behavior.
