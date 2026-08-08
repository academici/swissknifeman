---
id: D28
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P1 замораживает пять отдельных contracts в порядке run → slice → authority → worker → economy; каждый несёт Markdown + independent JSON cases + stdlib validator, а P1.5 — aggregate manifest/validator. RAG:— (repo-grounded: `research/07-p1-contract-freeze-design.md`).

## Почему

Mega-contract стирает ownership/versioning; один общий validator даёт поздним items возможность переинтерпретировать ранние expected outcomes.
