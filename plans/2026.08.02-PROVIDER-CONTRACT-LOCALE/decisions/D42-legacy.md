---
id: D42
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

The observed `harness hooks --target . --provider codex --observer --trusted --dry-run` failure is a public CLI target-normalization defect: P0.1 records it as non-green baseline evidence, P3.2 owns the forward implementation/regression fix at the Harness boundary, and P7.2 permanently smokes relative and absolute targets with equal planned operations and zero writes. The shared lock invariant remains explicit absolute roots. RAG:— (repo-grounded: exact reproduction in `findings/12-design-audit-remediation-2026-08-03.md`, `packages/harness/lib/harness/hooks.py`, `core/provider/lock.py`).

## Почему

Green direct unit imports did not exercise the source→target public control path; assigning one implementation owner and one release regression prevents the false-green from recurring without weakening core safety.
