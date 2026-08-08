---
id: D72
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P3.4 reads the complete execution-input chain in normative order: frozen P1.2 slice contract/cases/validator → terminal P2 compiler/test → frozen P1.3 authority contract/cases/validator and terminal authority/scheduler tests → frozen P1.4 worker contract/cases/validator → terminal P3 provider adapters/parity → terminal P2 CLI/test. Aggregate manifests remain later integrity gates. The item may add only the manifest-to-activity adapter, bounded runner and explicit provider/one-slice CLI binding; no second slice/result/state contract is legal. P0/P1 bytes, terminal P2/P3.1–P3.3 artifacts, D34/D36–D40 and P3.4 scope/acceptance remain unchanged; the escalation is resolved and P3.4 returns to `⬜ Not started`. RAG:— (repo-grounded: `findings/P3.4-required-read-defect-2026-08-04.md`; `research/18-p3.4-execution-input-reconciliation.md`; frozen P1.2/P1.3/P1.4 carriers and terminal P2 seams).

## Почему

Hash-only manifests and implementation-only sources each omit contract meaning; the ordered owner chain lets the executor bind P3 additively without inventing activity fields, authority defaults, acceptance, or provider outcomes.
