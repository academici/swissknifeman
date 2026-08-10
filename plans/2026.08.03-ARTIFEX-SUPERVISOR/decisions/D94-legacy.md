---
id: D94
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P3.7 remains owner only of `packages/task/tests/test_task_contract.py`. Its fresh P3.6 provider probe must write to a disposable `mktemp -d` output directory; the committed P3.6 provider-smoke/manifest/parity carriers are checked clean before and after and consumed read-only by their validators. No P3.6 output or terminal/history field is added to P3.7 `Files`. RAG:— (repo-grounded: `artifacts/P3/probe-adapters.py` output behavior, P3.6/P3.7 ownership and `research/29-audit8-authority-generator-reconcile.md`).

## Почему

Phase-wide requalification stays executable without foreign-scope mutation or capture; a before/after diff in a P3.6 carrier keeps P3.7 open.
