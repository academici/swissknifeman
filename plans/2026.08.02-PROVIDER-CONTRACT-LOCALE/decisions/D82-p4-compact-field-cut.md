---
id: D82
date: 2026-08-15
status: accepted
item: P4.1
items: [P4.1, P4.2, P4.3, P4.4, P4.5, P4.6]
supersedes: []
superseded_by: null
---
## Решение

Владелец зафиксировал компактный field cut P4: завершить пригодную к реальной обкатке
repository-local версию, а не продолжать массовую миграцию и циклы checkpoint/review.
P4.4 принимается как существующий canonical Task locale/fallback с честным отклонением
по незавершённому immutable-checkpoint carrier; P4.5 — как source-only compact prose cut в
`core`, Harness и mAInd; P4.6 — как штатная регенерация registry и provider projections с
двухпровайдерным readback. Полная миграция оставшегося corpus и development docs не является
частью field cut и перенесена в roadmap.

Это phase-scoped owner override: `phase-close: direct-green-validation`.

## Почему

Пользователь явно выбрал проверяемую рабочую версию без раздувания циклами. Наблюдаемая
runtime parity уже подтверждена локальными provider checks и read-only health на реальных
проектах; дальнейшая массовая редактура документации не улучшает этот первый field signal.

## Consequences

P4 закрывается как `🟠 Done with deviations`. Не меняются frozen contracts, provider meaning,
consumer-project files, trust, credentials или generated outputs вручную. Future corpus/docs
migration остаётся отдельной speculative roadmap work и начинается только от измеренной
field-потребности.
