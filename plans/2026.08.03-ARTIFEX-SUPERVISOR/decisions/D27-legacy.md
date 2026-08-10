---
id: D27
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Design budget registrar исправлен с 3 до 8 проходов: bootstrap + отдельные cold-start P0–P6, затем `finish`; это уточняет D21 без изменения семи фаз. **Consequences:** до исполнения добавляются пять обязательных design-сессий P2–P6. RAG:— (repo-grounded: plan-protocol phase-by-phase pipeline; seven-phase board).

## Почему

Старый знаменатель достигался уже на P1 и противоречил обязательному handoff на оставшиеся скелеты; качество ecosystem-core плана важнее преждевременного `finish`.
