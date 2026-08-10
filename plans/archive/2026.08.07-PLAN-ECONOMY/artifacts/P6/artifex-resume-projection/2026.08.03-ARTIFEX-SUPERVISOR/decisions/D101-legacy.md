---
id: D101
date: 2026-08-05
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Direct owner instruction resolves P4.4's stale copied `Статус: ok` literal: D100's exact clean/noop result `Статус: green` governs P4.4's independent same-target read-only recheck as well. The no-warning/stale/update predicate, exact provider/target/flags, one-repair limit and P4.4 prohibition on `--repair` remain unchanged. **Consequences:** P4.4 returns to `⬜ Not started` and continues under the corrected literal; the prior blocked finding remains append-only provenance. RAG:— (direct owner instruction; repo-grounded D100 and current Harness dry-run).

## Почему

The status spelling is an owner-surface fact, not a security relaxation; retaining every other fail-closed predicate preserves the P4.4 boundary.
