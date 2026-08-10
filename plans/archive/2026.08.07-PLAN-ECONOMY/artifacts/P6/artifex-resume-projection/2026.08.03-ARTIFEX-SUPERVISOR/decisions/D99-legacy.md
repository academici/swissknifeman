---
id: D99
date: 2026-08-05
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

D99 supersedes only P4.1's current-tree-only interpretation of “all terminal P0/P1/P2/P3 validators are GREEN”; it does not supersede D74/D77/D81/D89, frozen evidence, or P3 deviations. The P1.6 admission validator is GREEN only when executed from the complete P1.6 bookkeeping snapshot `89c4b3fe`, after proving item commit `140a9b53` is its ancestor and P1.6 contract/cases/validator/task/grant bytes are identical across both commits. The current-tree invocation remains an exact negative drift probe that must refuse `PARENT_ITEM_AS_TASK`; current P2/P3 successor/admission/runtime/G1 validators must independently be GREEN on the live pre-P4 generation. **Consequences:** P4.1 pays one isolated historical-snapshot validation and explicit dual-generation fan-in before artifact generation; `140a9b53` alone is no longer a reproducible validation snapshot, the current-tree P1.6 command is never counted as GREEN, and any missing anchor/blob, changed P1.6 byte, unexpected refusal or red current successor gate blocks P4.1. RAG:— (repo-grounded: `findings/P4.1-terminal-precondition-blocked-2026-08-05.md`; `research/31-p4.1-terminal-validator-generation-reconcile.md`; D81/D89 generation precedent).

## Почему

A validator coupled to a plan-item content hash is generation-relative: replaying it against a later lawful successor spec creates a false current-equality gate, while replaying it in the complete recorded snapshot plus current successor validators preserves both GREEN proof and forward-only provenance.
