# Отложенное из ремонта цикла исполнения

Статус: идеи, не начаты. Источник: задача «ремонт цикла исполнения» 2026-10-22 (workspace tasks, вне git; раздел
«Не в этой задаче») и её независимое ревью (codex/gpt-6-astra, 2026-10-22). Здесь только то, чего ещё нет ни в
плане PLAN9, ни в других ideas; уже учтённое — ссылкой.

## Новое

1. **Общий кэш зелёных проверок исполнитель ↔ conductor.** После T1 исполнитель сам прогоняет быстрые тесты затронутых
   модулей, conductor затем прогоняет приёмку заново. Кэши разделены в T1: под `SKM_CHECK_RUN` affected-tests
   читает только `run-<id>.json` своего run, `green.json` самопроверки приёмкой не засчитывается. Совместный кэш сэкономил бы повторный прогон,
   но только с подписью записи вне sandbox (ключ, недоступный исполнителю). Делать после замеров T1 на P4.3:
   если повторный прогон приёмки заметен в журнале. Владелец: orch + scripts.
2. **Изоляция Grok от личных skills и slash-команд владельца.** В `init` потока executor P4.2
   (`cnd-20261022T034954Z-e281a6/P4.2/attempts/1/streams/executor.2.jsonl`) видны `user:docs`, `morning`,
   `google-workspace` и другие личные команды. Вероятный вклад в долгое чтение и размер контекста; не измерено.
   Владелец: P6.1 (профили изоляции провайдеров), добавить как наблюдение.
3. **Фиксированная сигнатура находки ревью.** T4 считает прогресс по числу открытых Major; устойчивая идентичность
   находки между кругами (location — свободная строка, `review-findings.schema.json:72`) позволила бы точнее.
   Владелец: P7.1 (ключи находок в квитанции ревью).

## Уже учтено — не дублировать

| Что | Где |
|---|---|
| Autopilot (`orch conduct autopilot`) | PLAN9 P8.5 — после ремонта цикла, иначе автоматизирует потери |
| Сжатие prompt 90–138 КБ | PLAN9 P6.6 |
| Heartbeat, supervisor, orphan роли сверх T7 | PLAN9 P8.1, P8.2 |
| Миграция чужих путей из aicore | `ideas/2026-10-22-aicore-independent-foundation.md` |
| Индекс схем, кэш `$ref` (не измерено) | `ideas/2026-10-22-collect-validation-failures-and-speed-up-schemas.md` |
| Модели scout, лестница моделей | `ideas/2026-10-22-economy-models-for-context-scout.md` |
| GUI terminal race | `ideas/2026-10-22-terminal-credit-reservation-and-close-races.md` |
| CLASH `KeyError 'reused'` (OPEN) | `knowledge/operator-report` `p4-check-reuse-clash-001` |
| Generic lease для общих ресурсов | `ideas/2026-10-22-edufy-plan2-p42-orchestration-failures.md` §C — сначала простая политика последовательных юнитов |
| Хранилище метрик, dashboard, benchmark | отвергнуто владельцем (`knowledge/autopilot-operator`, owner stop 22 Oct) |
