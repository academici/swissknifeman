---
id: D1
date: 2026-09-20
status: superseded
item: P1.1
items: [P1.1, P2.1, P3.1, P4.1, P5.1]
supersedes: []
superseded_by: D3
---
# D1 — Five-phase rolling wave and phase-detail model gate

**Actor:** gpt-5.6-sol/high
**Evidence:** RAG:✅ 2026-09-20 official xAI/Cursor model pages + RAG:— local `agent --list-models` and owner brief

## Решение

План состоит из пяти крупных фаз, детализируемых по одной в три ограниченных захода.
Для detail pass выбирается Grok 4.6, если evidence packet широкий/cross-project или требует
внешней tool orchestration; Composer 2.5 — если packet bounded и работа Cursor-local.

## Почему

Альтернативы: детализировать все фазы сразу либо закрепить одну модель на весь план.
Обе альтернативы игнорируют новые evidence и разный характер wide discovery и bounded local slicing.
Проверенные различия моделей — capacity/tool surface, а не гарантия quality.

## Consequences

P1–P3 на старте рекомендуют Grok 4.6; P4–P5 — Composer 2.5. Фактический route
перепроверяется в начале каждой детализации; модель не меняет acceptance и не заменяет Task route evidence.
