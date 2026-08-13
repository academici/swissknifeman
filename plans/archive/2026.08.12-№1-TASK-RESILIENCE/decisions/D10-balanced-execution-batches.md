---
id: D10
date: 2026-08-12
status: accepted
item: P0.3
items: [P0.3, P1.1, P1.2, P1.3, P2.1, P2.2, P3.1, P3.2, P3.3, P4.1, P4.2, P5.1, P5.2, P5.3, P6.1, P6.2, P6.3]
supersedes: []
superseded_by: null
---
## Решение

Каждый item нового layout-v2 плана имеет обязательный `Batch` либо `solo` в §3 Routing.
Adjacent items одной фазы объединяются, когда общий producer/consumer, reads, setup или Validation
экономят время и токены; per-item lifecycle остаётся полным внутри группы. `solo` требует конкретной
hard/economy boundary. Batch не пересекает phase audit/close, не смешивает Exec и передаётся в
каждый execution handoff вместе со всем оставшимся суффиксом. RAG:— (repo-grounded: research/03).

## Почему

Item-level route без session grouping заставляет повторно читать один контекст, а необязательное
поле исчезает из шаблона и handoff. Обратная крайность — искусственно огромная цепочка — скрывает
hard gates и переполняет context. Phase-local cohesion даёт проверяемую середину.
