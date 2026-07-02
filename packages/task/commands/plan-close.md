---
description: "План-протокол: закрыть/сверить item Pn.m по git-фактам или закрыть фазу Pn (таблицы, Phase Handoff, lint). Пинит Sonnet/low."
argument-hint: "<PLAN-ID> Pn[.m]"
model: sonnet
effort: low
---
Это РЕКОНСИЛЯЦИЯ/ЗАКРЫТИЕ по plan-протоколу. Ввод пользователя: «$ARGUMENTS».
Модель/effort запинены (Sonnet/low — механическая сверка, thinking тут жжёт токены без
пользы) — не переключай вручную. SSOT схем/статусов — скилл `plan-protocol`.
Статусы — 6 канонических строк байт-в-байт; правки статусов ТОЛЬКО по фактам.

## Режим `Pn.m` — реконсиляция item'а

1. Прочитай `plans/<PLAN-ID>/plan.md` (Status Board) и item Pn.m в `phases/Pn.md`.
2. Сверь заявленное с git-фактами: `git log --oneline -- <Files item'а>` ·
   `git diff <до>..<после> -- <Files>` — правки реально есть и соответствуют Scope Included?
3. Прогони команды из **Validation** item'а, зафиксируй результат.
4. Вердикт по фактам: подтверждено → `🟢 Done` (или `🟠 Done with deviations` + Known
   Deviations); **нет подтверждения (нет коммитов/диффа, Validation красная) — НЕ 🟢**:
   оставь/верни `🟡 In progress` или `🔴 Blocked` и напиши почему в Completion Notes.
5. Синхронизируй Phase Status и Status Board в `plan.md`; перезапиши `handoff.md`,
   если статус изменился.

## Режим `Pn` — закрытие фазы

1. Все items фазы терминальны (`🟢`/`🟠`/`⛔`)? Нет — перечисли нетерминальные
   с их статусами и ОСТАНОВИСЬ (фаза не закрывается частично).
2. Сведи таблицы: `## Phase Status` фазы ↔ статусы items ↔ строка фазы в
   `## 4. Phase Index & Status Board` (`Items 🟢/всего`, статус фазы) — без расхождений.
3. Заполни `## Phase Handoff` в `phases/Pn.md`: что сдали, известные отклонения
   (агрегат Known Deviations items), что дальше.
4. Перезапиши `plans/<PLAN-ID>/handoff.md` (Next: первый item следующей фазы или
   закрытие плана); добавь строку в `## 6. Update Log`.
5. Прогони `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan-lint.py" plans/<PLAN-ID>`
   (нет переменной/скрипта — предупреждение и пропуск); красное почини.

**Expected output:** таблица сверенных статусов (`ID | было | стало | основание`) +
финальная строка «PHASE-CLOSED: Pn» либо список блокеров, почему фаза не закрыта.
