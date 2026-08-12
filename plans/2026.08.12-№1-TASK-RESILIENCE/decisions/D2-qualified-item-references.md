---
id: D2
date: 2026-08-12
status: accepted
item: P1.2
items: [P1.2, P4.3]
supersedes: []
superseded_by: null
---
## Решение

В коде, docstring, PR/review comments item именуется полной формой `<PLAN-ID> Pn.m`; bare `Pn.m`
допустим только внутри носителей самого плана. RAG:— (owner-grounded: `brief/00-brief.md`).

## Почему

Одинаковые `P1.2` существуют во многих планах; вне plan-local context голая ссылка коллидирует.

