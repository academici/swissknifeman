---
id: D1
date: 2026-08-12
status: accepted
item: P1.1
items: [P1.1, P1.2]
supersedes: []
superseded_by: null
---
## Решение

Новые планы используют `YYYY.MM.DD-№N-CODE`, где `N` — положительный уникальный внутри даты
номер; Title начинается с `План №N —`. Legacy IDs остаются readable. RAG:—
(owner/repo-grounded: `brief/00-brief.md`, `findings/00-roadmap-and-runtime-gap.md`).

## Почему

Полный ID без ordinal не выполнял явную директиву владельца и не давал визуального номера плана.
