---
id: D71
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P3.3 reads the complete frozen P1.4 conformance triplet in normative order — `worker-envelope-v1.md` → `worker-envelope-cases-v1.json` → `validate-worker-envelope.py` — before either provider adapter, while the aggregate P1 manifest/validator remain later hash/fan-in checks. Contract-only, case-only and manifest-only inputs are rejected because none alone exposes both the neutral taxonomy and its executable mutation semantics. P0/P1 bytes, D12/D36–D38, P3.1/P3.2, P3.3 scope and acceptance remain unchanged; the spec escalation is resolved and P3.3 returns to `⬜ Not started`. RAG:— (repo-grounded: `findings/P3.3-required-read-defect-2026-08-04.md`; `research/17-p3.3-required-read-reconciliation.md`; frozen P1.4 carriers).

## Почему

The executor can now derive every parity row and expected refusal from finite pinned inputs without inferring contract semantics or treating an aggregate hash manifest as the contract body.
