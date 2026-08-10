---
id: D131
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P5.6's Implementation Rule (5) required every commit intervening on the P4 anchor «to touch only P4 evidence paths», which rejects the ONLY correct anchor `3533234c` — a legitimate P4.7 remediation (`fix(harness): восстановить committed-tree validation P4`) that repaired the P4 validators and the harness half of the same defect in one `Files`-scoped commit. The rule is reformulated: the P4-EVIDENCE PORTION of each intervening commit's diff must be owned by a P4 item or the P4 phase close; other paths in the same commit are recorded and do not stop the item, while a P4-evidence change no P4 item accounts for still does. The new anchor is corroborated twice independently: `git diff --exit-code 3533234c -- phases/P4.md artifacts/P4` is empty, and the frozen P5.1 `trial-catalog-v1.json` pins the same tree as its `source_tree_ref`. Boundary: `124df816` also names the owning snapshot of the historical P4.8 leaf validator (P5.1 Scope/Rules/Validation, D106) and those occurrences do NOT move. RAG:— (repo-grounded: `findings/P5.6-gate-staleness-verification-2026-08-06.md` §4–§5)

## Почему

Правило смешивало «легитимна ли правка P4-улик» (существенный вопрос) с «трогал ли коммит что-то ещё» (к path-scoped `git diff` отношения не имеет) и гарантировало вторую эскалацию на собственном верном якоре
