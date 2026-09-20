---
id: D2
date: 2026-09-20
status: accepted
item: P1.1
items: [P1.1, P2.1, P3.1, P4.1, P5.1]
supersedes: []
superseded_by: null
---
# D2 — Measure before implementation, with a bounded evaluation budget

**Actor:** gpt-5.6-sol/high
**Evidence:** RAG:— owner brief, `task-development-philosophy`, repository telemetry baseline

## Решение

В P5 попадают только срезы с verdict `go`, подкреплённые repository evidence, небольшим
matched experiment и описанным practical effect. Обычный выход из неоднозначности — `defer`
или `keep`, а не новый gate. Глубокая test-программа и полная статистическая валидация вне scope.

## Почему

Альтернатива — сразу реализовать P0/P1 рекомендации из исходного аудита. Его автор не
имел локального checkout и сам пометил гипотезы как непроверенные. Обратная крайность — дорогой
длительный benchmark — противоречит owner scope и сама может стать новой машинерией.

## Consequences

Каждая phase detail называет stop rule, бюджет прогонов, метрики и порог practical effect.
P5 может оказаться маленькой или пустой; это допустимый успех плана.
