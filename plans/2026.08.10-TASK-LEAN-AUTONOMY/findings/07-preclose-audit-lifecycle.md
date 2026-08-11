# P1.1 — pre-close audit lifecycle

**Дата:** 2026-08-11  
**Тип:** repo-grounded protocol finding  
**Статус:** accepted as D14 input

## Наблюдение

В `packages/task/commands/plan-audit.md` audit описан как проверка закрытой фазы, а
`packages/task/commands/plan-close.md` делает phase close нормальным предшественником audit.
В живом consumer плане `agelto/plans/2026.08.09-RELEASE-READINESS` handoff после P2.7 задаёт
`task:plan-close ... P2`, затем fresh `task:plan-audit ... P2`; P2.7 также упоминает terminal
reconciliation P2.1–P2.6. Последнее — допустимая сверка evidence items, но не должно означать,
что `plan-close Pn.m` является нормальной next-командой.

## Риск

Получается цикл `close → audit RED → repair/design → close → audit`. Фаза формально закрыта до
того, как известен verdict качества; пользователь видит лишние сессии и неочевидный выбор между
phase close и item close.

## Принятая граница

D14 переносит audit перед phase close: terminal items образуют unclosed candidate, audit GREEN
фиксирует свежий fingerprint, и только он разрешает `plan-close Pn`. RED и unresolved
`ATTENTION` оставляют фазу кандидатом, направляют repair в owning item и требуют re-audit.
`plan-close Pn.m` остаётся только recovery path для legacy/incomplete reconciliation и исключён
из normal Next. Это является P1.1 Task-source change; Agelto не изменяется до появления этой
совместимой runtime semantics.
