# Разбор Agelto 23–24.10: что исправлено и что остаётся

Источник: `artifacts/autopilot/orchestrator-retrospective-20261024/report.txt` (проект agelto, машина оператора).

## Исправлено в этой ветке (work-3)

- Цикл доработок без предела (разбор Haiku на пункте 8.5): `plan.py unit rework` отказывает с `REWORK_LIMIT` после `policy.review_rounds_max` доработок одного юнита. Владелец модуля: `packages/planner/lib/planner/plan/units.py`.
- Ручная процедура без вердикта тратила коррекции и заканчивалась `CHECKS_RED` (разбор §6, E07/E08): теперь `MANUAL_PENDING` без траты бюджета. Владелец модуля: `packages/orch/lib/orch/conductor/stages/checks_stage.py`.
- Хуки из workspace при машинном слое (PR #162, коммит `51bed50`): перенесён без коммита локальных проекций `979fcb3`.

## Не исправлено: нужен отдельный пункт плана

- §1 Preflight расходится с фактическим admission (класс модели, привязка checkout). Владелец: `orch` preflight/routing, `planner` plan/store.
- §2 Проверки с общим одноразовым ресурсом идут параллельно при defaults `parallel=2`, `reuse=true`. Нужны объявления общих ресурсов. Владелец: `orch` check scheduling, объявления consumer workflow.
- §3, §4 Нет typed-квитанции доставки промпта и ёмкости (provider receipt). Владелец: интеграция провайдера в `orch`/`aicore`.
- §5 Нет продолжения с новым контекстом для того же пункта (`--batch` принудительно выбирает handoff). Владелец: `orch` conductor, native continuation.
- §6 `manual_pending → materialization → fenced completion` как полноценное состояние (сейчас только остановка без траты бюджета). Владелец: `orch` checks/source lifecycle, `planner` lifecycle.
- §7 Историческая `last_stop` видна в статусе как активная причина. Владелец: `orch` supervisor/status (`supervisor.py`, `run_service.py`).
- §7 Progress fingerprint для повторного отказа одной и той же проверки. Частично есть в `checks_stage.py` (`progress`), не покрывает ручной цикл вне конвейера.

## Не является дефектом SKM (по разбору)

- Снимок 58 выбран по ошибке оператора; поздний authentic 61 лежит в Git.
- Конвенция WorkState/exhaustive и CASCADE — ошибки канона consumer-проекта.
- Ложные `SchemaInventory` ошибки — исправлены сравнением строк/типов в `93077`.
