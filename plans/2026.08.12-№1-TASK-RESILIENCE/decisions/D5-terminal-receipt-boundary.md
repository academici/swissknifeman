---
id: D5
date: 2026-08-12
status: accepted
item: P4.1
items: [P4.1, P4.2, P4.3]
supersedes: []
superseded_by: null
---
## Решение

Task публикует byte-bound terminal delivery receipt с exact persisted Next, journal pointer,
commit и carrier digests; nonterminal субъект получает `FINAL_BEFORE_TERMINAL_FORBIDDEN`.
Transport heartbeat/final interception остаётся честной harness/provider boundary. RAG:—
(repo-grounded: `roadmap/2026.08.11-terminal-final-continuity-receipt.md`,
`roadmap/2026.08.11-terminal-handoff-recommendation-receipt.md`).

## Почему

Prompt-only final contract не связывал chat termination с durable terminal plan state и терял recommendation.
