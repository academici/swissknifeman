---
id: D24
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P0 freeze хранится тройкой «читаемый Markdown + нормализованный JSON + stdlib verifier»; raw provider streams, prompts, chain-of-thought, secrets и environment dumps в evidence bundle не входят. RAG:— (repo-grounded: evidence-integrity/untrusted-content canons and `research/06-p0-evidence-freeze-design.md`).

## Почему

Человек должен видеть основания, а следующий дешёвый исполнитель — проверять форму без доверия к прозе или сырым модельным данным.
