---
id: D30
date: 2026-08-02
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P6 freezes `provider-health-v1` as a composition contract over package-owned evidence: Skiller owns selection/dependencies/budget, Harness owns profiles/trust/settings, P3/P4 own provider and locale readback, and mAInd owns exact-set fleet orchestration. RAG:— (repo-grounded: `findings/10-p6-health-control-recon-2026-08-02.md`, `research/06-p6-health-parity-design.md`).

## Почему

Existing commands cover different axes; a monolithic parser would duplicate their semantics, while composition preserves ownership and stable diagnostics.
