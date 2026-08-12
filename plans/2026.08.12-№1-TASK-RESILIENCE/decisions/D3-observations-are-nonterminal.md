---
id: D3
date: 2026-08-12
status: accepted
item: P2.1
items: [P2.1, P2.2]
supersedes: []
superseded_by: null
---
## Решение

`routing-rejected`, `decision-pending`, `local-repair` и `block-candidate` — observation results:
они пишут provenance, но не меняют state и attempt. RAG:—
(repo-grounded: `roadmap/2026.08.11-local-repair-vs-escalation-classifier.md`,
`roadmap/2026.08.11-codex-effective-route-observability.md`).

## Почему

Предстартовый отказ или безопасная локальная починка не являются terminal outcome продуктовой работы.
