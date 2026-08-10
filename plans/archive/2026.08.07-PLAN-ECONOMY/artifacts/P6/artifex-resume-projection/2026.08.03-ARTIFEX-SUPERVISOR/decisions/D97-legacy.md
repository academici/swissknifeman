---
id: D97
date: 2026-08-05
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

D97 supersedes D91 and D92 only as active machine-authority carriers: P3.8 requests D95's `G-OWNER-P3.8-HARNESS-INSTRUCTIONS-R2`, while P6.1 and P6.2 request D96's `G-OWNER-P6.2-HARNESS-ROOT-INSTRUCTIONS-R2`; D91/D92 remain immutable evidence of the malformed audit-8 attempt. D86/D87, approved path sets, consumers, D93 generator ordering, D94 validation isolation, item statuses and G1→G5 topology do not change. **Consequences:** live phase/roadmap/audit carriers must use D95/D96, historical prose may continue to name D91/D92 as provenance, and any request using an old or widened gate/scope still fails closed. RAG:— (owner/repo-grounded: `brief/17-audit9-resolver-valid-owner-carriers.md`; `research/30-audit9-resolver-valid-authority-reconcile.md`; exact resolver grammar in `packages/task/lib/task/task_contract.py`).

## Почему

A second row with either old gate marker would remain ambiguous by construction; fresh exact identities preserve append-only history while making each protected transition machine-consumable.
