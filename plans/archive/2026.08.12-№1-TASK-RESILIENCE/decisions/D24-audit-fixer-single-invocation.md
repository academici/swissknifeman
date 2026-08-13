---
id: D24
date: 2026-08-13
status: accepted
item: P5.2
items: [P5.2, P5.3]
supersedes: []
superseded_by: null
---
## Решение

Phase audit становится audit-fixer: свежий независимый audit root сам
исправляет все безопасные in-scope находки, повторяет исходную Validation,
регенерирует state/status/bundle, пересобирает candidate и только затем
публикует финальный verdict. Штатный audit больше не выдаёт отдельный
repair-run, второй audit или автоматический design-pass. `AUDIT-ROOT-TERMINAL`
остаётся границей только после финального verdict. RAG:— (owner-grounded:
`brief/01-refinements.md`; repo-grounded: `findings/15-P5-audit-fixer-redesign.md`,
`research/08-P5-audit-fixer-design.md`).

P5.2 владеет canonical Task audit-fixer/runtime seam и focused acceptance. P5.3
потребляет этот committed producer, синхронизирует EN-only plan-protocol и все
generated provider/registry/docs carriers, затем выполняет aggregate validation.
Незапущенный P5.3 для P5.2 — `dependency-not-ready`, а не terminal block.

## Почему

Текущая read-only цепочка сама порождает дорогие рестарты и даёт
исполнителю ложную возможность остановиться на сложности, не доказав
реальную границу. Фазы уже ограничены по объёму, поэтому их in-scope
отклонения входят в обычный бюджет одного audit root. RAG:— (owner-grounded:
`brief/01-refinements.md`; repo-grounded: `packages/task/commands/plan-audit.md:7-10,168-177`).

## Consequences

Audit больше не read-only: он получает ограниченное право на product writes только
в union заявленных phase item `Scope`/`Files` и для доказанного bounded incidental repair.
Каждая правка по-прежнему проходит item contract, exact Validation, product/bookkeeping
commits и candidate rebinding. Public/frozen, authority и safety границы не
ослабляются; только они могут остановить штатный audit-fixer.
