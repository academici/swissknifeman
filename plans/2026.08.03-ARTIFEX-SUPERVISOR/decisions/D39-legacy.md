---
id: D39
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P3.4 binds adapters through P2's typed activity port and adds only explicit provider selection plus hard `--max-slices 1` to existing `start`/`resume`; omission preserves P2's no-provider refusal. RAG:— (repo-grounded: D34 and `research/09-p3-provider-adapter-design.md`).

## Почему

Provider integration stays additive, one scheduler/state machine remains authoritative, and the prototype cannot become an unattended wave before P4/P5 evidence.
