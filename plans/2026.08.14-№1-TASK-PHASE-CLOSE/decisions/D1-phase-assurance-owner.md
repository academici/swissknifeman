---
id: D1
date: 2026-08-14
status: accepted
item: P1.1
items: [P1.1, P1.2]
supersedes: []
superseded_by: null
---
## Решение

`packages/task/lib/task/phase_assurance.py` становится единственным stdlib-only owner
схемы `phase-assurance/v1`. Блок содержит ровно пять ordered fields; direct close
совместим только с isolated/no-seam/non-live declaration.

## Почему

Общий parser нужен gates и lint; его размещение в `plan_gates.py` замыкает
существующий import cycle. Missing legacy block читается, но не даёт direct close.

**Evidence:** RAG:— (`findings/02-assurance-schema-recon.md`, `findings/04-adversarial-verification.md`).
**Actor:** design/gpt-5.6-sol/high.

## Consequences

Plan lint и runtime импортируют один parser; duplicate regex/enums запрещены. Canonical
skill/reference/template меняются синхронно.
