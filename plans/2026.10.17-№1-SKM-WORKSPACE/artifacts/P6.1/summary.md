# P6.1 — dry-run миграции, машина A (2026-10-18)

**Итог: готово к MIGRATE-HOST-A: НЕТ** — `workspace migrate plan` не выполнен ни для одного проекта.

## Блокер сводки
`migrate plan` для всех 7 проектов падает с `WORKSPACE_NOT_INITIALIZED` (см. `migrate-plan-errors.txt`): workspace
на машине A ещё не создан (`~/.local/share/swissknifeman/workspace` отсутствует), а `workspace init` и
`project attach` (runbook host-a, шаги 1–2) в P6.1 запрещены (item.rules[0]). Отчётов `migrate-plan-<p>.json` нет —
поэтому блокеры (секреты, большие файлы), warn по правилам publish-safety и local-only объём **не определены**.
Дополнительно: внутри launcher/conductor запуска `SKM_WORKSPACE_ROOT` указывает на каталог кода модуля
(`.../packages/workspace`), а не на данные workspace — резолвер читает его как корень workspace. Без переопределения
в живых запусках из launcher `init` создал бы workspace внутри каталога кода; владельцу нужно запускать migrate из
чистой оболочки или исправить коллизию имён.
Предлагаемое действие: владелец (или отдельный пункт) выполняет `workspace init` + `project attach` (без apply), затем
P6.1 повторяется для `migrate plan`.

## Таблица проектов (источник: migrate-discover.json, runs-*.json, plans-before-*.json)
| Проект | v4 планы (всего) | legacy-каталоги | файлов | байт | Планы по `planner plans` до миграции | in_progress-пункты | Блокеры migrate plan | Живые runs |
|---|---|---|---|---|---|---|---|---|
| billium | 1 | 0 | 314 | 4 793 279 | PLAN1 active 21/33 | не определено (нужен migrate plan) | не определены (plan не выполнен) | нет |
| commerz | 1 | 0 | 460 | 26 096 754 | список пуст (единственный план archived) | не определено | не определены | нет |
| azguard | 2 | 1 | 2863 | 145 077 858 | PLAN1 done 45/45; PLAN2 active 11/28 | не определено | не определены | нет (9 runs в статусе stopped, ITEM_BLOCKED/CLAIM_BLOCKED/WORKTREE_DIRTY — не живые) |
| chatom | 2 | 4 | 6547 | 236 008 612 | PLAN3 done 74/74; PLAN4 active 49/54 | не определено | не определены | нет |
| corex | 2 | 5 | 12641 | 833 028 898 | PLAN2 paused 176/178 (PLAN3 active по inventory, но не в списке planner plans — проверить) | не определено | не определены | нет |
| vaulter | 2 | 10 | 9746 | 834 372 723 | PLAN3 active 67/74 | не определено | не определены | нет (runs-vaulter.json: нет status running) |
| swissknifeman | 5 | 0 | 1612 | 19 690 421 | PLAN3 active, PLAN4 active, PLAN5 done, PLAN6 active 14/19 | не определено | не определены | 1 running: cnd-20261018T001549Z-1018e4 (items P6.1) — это сам текущий run P6.1; к apply должен быть завершён |

Все 7 проектов: `sources` launcher+registry (swissknifeman — только launcher), маркер `.swissknifeman/project.json` ещё не создан (`marker: null`).

## Классы каталогов (по discover, D12)
v4 (plan.json v1, переносятся как планы): 15 из 7 проектов. legacy (не-v4, байт-в-байт в legacy-plans/): 20 каталогов
(azguard 1, chatom 4, corex 5, vaulter 10). derived/local-only: не определены без migrate plan. Объём plans/ всего ≈ 2,1 ГБ.

## Замечания
- Расхождения с inventory (code-facts): legacy corex 5 (inventory: 4), azguard v4 2 (inventory: PLAN1 + новый PLAN2), vaulter v4/legacy 2/10 — совпадает; объёмы выросли с момента инвентаризации.
- discover также нашёл вне списка 7: skm-wt-clean, skm-wt-plan6 (git worktree swissknifeman), sockit — не мигрируются.
- Никаких записей в состояние проектов не выполнено; `git status` проектов не затронут этим пунктом.
