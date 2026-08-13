---
id: D23
date: 2026-08-13
status: accepted
item: P4.1
items: [P4.1, P4.2]
supersedes: []
superseded_by: null
---
## Решение

AUDIT-CAP: третьего Audit P4 нет; фаза закрывается штатным `task:plan-close`.

Владелец разрешает точечный repair-forward P4.1 без нового audit: принять уже
закоммиченный `168b576a` как реализацию exhaustive continue-first signal matrix и
повторить только его focused validation. Новых terminal attempts после закрытия фазы
не допускается.

## Почему

Второй аудит нашёл обход, но текущий committed tree уже содержит минимальный фикс и
регрессию в declared P4.1 Files. Повторный аудит запрещён исчерпанным cap, а расширение
scope или новая provider/docs работа не требуются.

## Consequences

`task:plan-close` вызывает phase-close gate с `owner_decision="D23"`; P4 закрывается
по фактическому результату focused validation с сохранением P4.2 material deviation.
P0–P3, P5–P6, stable спецификации P4.1–P4.2 и provider projections не изменяются.
