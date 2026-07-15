# HANDOFF — 2026-07-15 — after P2.1

**Next:**

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — дефолт §9, детерминированные гейты (check-translations/registry/validate) |
| Context | continue (/clear) — ручной item |
| Суть | Расширить CORE-скилл anti-drift подсекцией file-op-гигиены (read-before-edit + якорь-гигиена + анти-reread) на основе вердикта P2.1 (RU→EN регенерация) |

```
/task:plan-exec 2026.07.15-TELEMETRY-OPT P2.2
```

**Done:** P2.1 закрыт (`f173c0b`) — пере-агрегация 114 run-reports (`findings/churn-agg.py`,
окно идентично `agg.py`): Edit/Write `tool_failures` 55 (43 not-read-first + 8 string-not-found
+ 3 not-unique + 1 deny-permission), `reads.top_rereads`-сумма (extra) **342** — доминирующий
драйвер churn (на порядок выше edit-fail-кластера). Расхождение с baseline-числами (46/16/392)
объяснено дрейфом 4-дневного окна между снапшотами, направление/порядок величины совпадают.
Нативный read-гейт Edit/Write подтверждён repo-grounded по ФАКТУ (все 43 not-read-first снипета
несут дословный текст ошибки тула, не только контракт). Вердикт формы вмешательства:
**дисциплина** (P2.2), НЕ добавочный хук-сигнал — reread не ловится категоризацией ошибок
(не `tool_failures`-запись), `analyst` не читает существующее сырьё (`tool_failures`/
`top_rereads`) — новый срез лёг бы невостребованным. OQ-3 → Resolved (совпал с дефолтом D6, новой
D-записи не потребовалось). См. `findings/P2-churn-inventory.md`.
**Remaining:** P2.2 (file-op-гигиена в `anti-drift`, дом её деталей — findings P2.1 выше) →
фаза P2 терминальна → P3/P4 (скелеты, детализация по `/task:plan-design`) → P5 discovery.
**Sources of truth:** plans/2026.07.15-TELEMETRY-OPT/plan.md · phases/P2.md ·
findings/P2-churn-inventory.md · findings/churn-agg.py ·
packages/skiller/skills/general/anti-drift/SKILL.ru.md ·
packages/harness/configs/claude-code/hooks/run-report/_lib.py (`reads`/`tool_failures`).
**Open risks:** нет новых. P2.2 обязан взять КОНКРЕТНЫЙ якорь-пример из P2.1 (not-read-first
доминирует, сконцентрирован в 2 проектах) — не абстрактное наставление (Code Guidance item'а).
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: как в P1 (детекция релончей между сессиями, разбор кейсов baseline построчно,
  чтение `<task-notification>` в run-report) — не изменилось.
- open_questions: OQ-1 (гранулярность P3-аудита, ждёт детализации P3). OQ-2 → D7 (закрыт).
  OQ-3 → Resolved (закрыт этим item'ом, см. Done выше).
