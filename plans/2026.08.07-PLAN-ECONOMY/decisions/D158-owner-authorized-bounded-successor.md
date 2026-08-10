---
id: D158
date: 2026-08-09
status: accepted
item: P6.9
items: [P6.2, P6.5, P6.6, P6.9]
supersedes: [D157]
superseded_by: null
actor: repository-owner/verbatim
---

## Решение

Владелец явно разрешил продолжить в текущей сессии до терминального результата. Literal owner
provenance: «или даже для этой сессии, чтобы до финала добить»; контекстом непосредственно перед
этим было требование дать команду, которая устраняет повторный design-loop. Это разрешает ровно
один bounded successor acceptance/repair после D155: исправить наблюдённые дефекты executor input
paths, заморозить v1.1.2 с неизменными predicates и выполнить один полный прогон.

D158 supersedes D157 structural waiting и только для successor v1.1.2 переносит change-control
ownership с исторического P6.7 на P6.9. D153–D156, frozen v1.1.1 raw/report и его `fail` остаются
неизменной историей. Threshold, unit, five-slot scope, admission reducer, arms, canary и
measurement implementation менять запрещено.

## Почему

D157 корректно остановил исполнение без owner authority, но после literal owner message его
повторный design-route превратился бы в self-loop. Наблюдённые failures конечны и относятся к
generated/read-path carriers, поэтому один versioned attempt можно ограничить проверяемым scope,
не ослабляя протокол и не выдавая v1.1.1 за успех.

## Bounded repair

Разрешены только: материализация отсутствующих generated bundles; сужение обязательного чтения
терминальных P6.2/P6.5/P6.6 до точных section selectors и provenance-complete terminal capsule;
регенерация затронутых bundles/states/views; frozen v1.1.2 и один acceptance attempt. Сужение не
может удалять работу или переписывать terminal evidence: capsule обязан сохранить source-set
digests, load-bearing facts и ссылки на полные carriers, а вмешательство публикуется в отчёте.

## Consequences

Если любая arm или canary не проходит exact frozen predicate, P6.9 закрывается терминальным
`Done with deviations`, ARTIFEX остаётся на паузе, и новый repair/design-loop не создаётся. Только
полный положительный результат обеих arms и canary разрешает снять `Paused By` в donor ARTIFEX и
закрыть ECONOMY. Ни один промежуточный успех не разрешает donor mutation.
