# Roadmap: покрытие analyst-цикла по флоту онбордженных проектов

**Статус:** отложено (данные есть, решения нет). **Критерий внедрения:** осознанное решение
по umbrella-политике хуков на чужих проектах — не одностороннее включение.

## Контекст

`analyst` (run-report → digest → уроки → token-report) даёт ценность только там, где
хук `run-report` реально включён и накапливает историю. Проверка флота (SKM-AUDIT-004,
P3.1/P3.2) показала: из ~20 онбордженных проектов лишь малая часть пишет run-report
вообще, и ещё меньше накопили analyst-state/token-trend. Отсутствие сигнала — не баг
`digest` (перепроверено read-only на трёх проектах, см. R3 в
`plans/SKM-AUDIT-004/findings/P3-recommendations.md`: `--dry-run` корректно резолвит
бинарь и легитимно возвращает `candidates: []`), а data-coverage gap: хук `run-report`
per-project настройка (harness-хуки), не глобальный демон.

## Замер (SKM-AUDIT-004, 2026-07-07)

- Run-report: **5/20** проектов накопили историю (agelto 30, azguard 10, vaulter 9,
  chatom 6, swissknifeman 4).
- Analyst-state (`~/.swissknifeman/analyst` per-project): **2/20** (agelto, vaulter).
- Token-trend (`analyst token-report`): **2/20** (agelto 42 записи, swissknifeman 4).
- Там, где хук включён и накопил историю (agelto), сигнал полезен —
  rolling-baseline уже считается штатно.

## Почему не внедряется сейчас (D6, SKM-AUDIT-004)

Массовое включение хука `run-report` на 15 чужих проектах разом — межпакетное изменение
конфигурации множества репозиториев, шире «safe reversible на одном проекте». Требует
решения по umbrella-политике, не «safe quick-win».

## Варианты (без обязательств)

1. Включить `run-report` хук по умолчанию для новых онбордингов (`maind onboard`/
   `harness hooks`) — не трогает уже онбордженные проекты, закрывает gap на новых.
2. Ничего не менять — данные появятся органически по мере использования проектов.
3. Добавить `analyst`-срез в `maind projects status`/`maind fleet` для видимости
   покрытия без отдельной команды на проект (наблюдаемость без изменения поведения).

## Источник

`plans/SKM-AUDIT-004/findings/P3-stats.md` (табл. 2) ·
`plans/SKM-AUDIT-004/findings/P3-recommendations.md` (R6).
