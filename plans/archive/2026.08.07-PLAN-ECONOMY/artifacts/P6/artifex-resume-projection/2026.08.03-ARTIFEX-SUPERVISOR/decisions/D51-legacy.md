---
id: D51
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P5.2 uses a stateless measurement harness over the P4-assured public CLI with `--max-slices 1` for exactly three sequential real repository slices in controlled disposable roots; the harness owns no transition, authority or acceptance state. RAG:— (repo-grounded: P3.4/P4 boundaries and `research/11-p5-pilot-economics-design.md`).

## Почему

Proves a live reversible path without changing the assured candidate hash or introducing a second scheduler.
