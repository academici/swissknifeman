---
id: D29
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P1 execution hard-gated на terminal P0 и green P0 validators; пока P0 0/5, его outputs именуются только как planned preconditions. Donor contracts цитируются, а не копируются; P1 добавляет только supervisor-owned seams. RAG:— (repo-grounded: `findings/05-p1-donor-reconciliation-2026-08-03.md`).

## Почему

Design может быть DoR до producer execution, но frozen values нельзя изобретать из будущих files или дублировать live Task/Harness carriers.
