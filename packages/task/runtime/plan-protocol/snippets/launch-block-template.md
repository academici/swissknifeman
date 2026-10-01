# Шаблон launch-block — фиксированная форма «что запускать дальше»

Каждая выдача реального следующего шага — handoff.Next и финалы отчётов
plan-run/plan-close/plan-audit — обязана иметь эту форму (SKILL раздел 6):
semantic carrier + таблица требований БЕЗ команды + отдельный копируемый блок команды
активного provider adapter.

`````markdown
**Next:** <kind>: task:<plan-command> <PLAN-ID> <arguments>

| Параметр | Значение |
|:--|:--|
| Batch | <Routing Batch ID / solo; n/a только для design/audit/close/archive> |
| Model class | <economy / implementation / frontier> |
| Effort | <low / medium / high / xhigh> |
| Capabilities | <минимальный набор semantic capability IDs; `—` если дополнительных нет> |
| Context | <enum: continue-root · isolated-child-return · cold-start-root (+ one reason)> |
| Суть | <1 строка: что делает запуск> |

**Provider-native command:**

```text
<provider-rendered invocation>
```
`````

**Команда всегда вне таблицы.** Активный provider adapter определяет форму: Claude Code
печатает native slash-команду в `text`-блоке, Codex — полный запуск `codex ...` в `bash`-блоке,
Cursor — `agent --workspace … --model … --force …` в `bash`-блоке (см. provider-model-roles).
Не печатай несколько native-форм. Предпочтительна одна физическая строка; если shell-команда намеренно
разбита, каждая продолжаемая строка, кроме последней, заканчивается `\`. Визуальный перенос
Markdown не считается продолжением shell-команды. Исполнимый Next без fenced command block
неполон; финал нельзя заканчивать на «готово», если следующий запуск существует.
GREEN item и eligible final-item phase закрываются до вычисления Next: нельзя печатать launch для
`plan-close` текущего результата или повторного `plan-run` текущего item.

Отдельный блок может нести provider invocation ИЛИ голый промпт:

- **owner-run step** (`manual:` Next) — no single command expresses it: the fenced block carries
  a BARE item prompt (or a `/model`+`/effort`+`/task:plan-run` sequence);
- **scope-payload** (находки/реопен, см. ниже) — code-block несёт invocation ПЛЮС
  четыре строки `РЕЖИМ:`/`ВХОД:`/`СКОУП:`/`НЕ ТРОГАТЬ:`, в одну строку таблицы не
  умещается;
- **форма `ОЖИДАНИЕ:`** (ниже) — code-block несёт guard-строку `# НЕ раньше: …`.

Legacy-строка таблицы `Команда` остаётся читаемой для старых планов, но новые handoff'ы её
не выводят. Канонический носитель команды — только fenced block.

`````markdown
<!-- example: an ordinary run item whose next step is fully expressed by one command -->
**Next:** run-items: task:plan-run <PLAN-ID> Pn.k

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Capabilities | — |
| Context | continue-root |
| Суть | закрыть Pn.k |

**Provider-native command:**

```text
/task:plan-run <PLAN-ID> Pn.k
```
`````

Правила:

- **Самодостаточность (cold-start).** Команда обязана работать из холодной сессии:
  plan-ID + пути входных доков (cold-start reads) + встроенное утверждение гейта,
  если исполнение гейтится. Ссылки вида «эта сессия» — только как дополнение.
- **Scope-payload — launch-block, несущий НАХОДКИ** (§8, D-канон 2026-07-17): вердикт
  `plan-audit` `RED`/`ATTENTION` и фикс-предложение C3/D6 голыми быть не могут. Правило
  целиком в SKILL разделе 8 (единственный SSOT), здесь форма — четыре строки под командой
  в том же code-block'е, порядок фиксирован:

  `````
  <provider-rendered invocation>

  РЕЖИМ: <реопен по §3 (4 шага) | детализация | ремедиация>
  ВХОД: <файл → блок с находками; cold-start read>
  СКОУП: <нумерованный список: что сделать>
  НЕ ТРОГАТЬ: <анти-скоуп: что оставить как есть>
  `````

  `plan-audit` кладёт этот launch-block подсекцией `### Что запускать` в конец своего блока
  `## Audit Pn` — чат машиной не проверяется, диск проверяется. `plan-lint` гейтит присутствие
  всех четырёх строк (датовые планы от 2026.07.16 — ERROR, старее — WARNING). `GREEN` находок
  не несёт — payload'а не требует.
- **Model class/Effort** — из Routing плана (SSOT-матрица — SKILL раздел 9); отклонение
  от матрицы обосновывается там же, не в launch-block.
- **Batch** — из Routing плана. Для execution Next указывается ID группы или `solo`, а команда
  адресует весь ещё не закрытый adjacent-суффикс группы. Поле не исчезает при новом handoff;
  `n/a` допустимо только для design/audit/close/archive шага без исполнения item'ов.
- **Capabilities** проверяются до invocation/work/write. Оркестрация обязана перечислить
  `command.subagents` и `command.workflow-carrier`; missing/unknown/unsupported блокирует запуск.
- **Context** — закрытый enum ТРЁХ значений SKILL §6; выбирается границей, а не командой:
  - `continue-root` — обычная последовательная работа и local repair;
  - `isolated-child-return` — один ограниченный reviewer/worker возвращает evidence root'у;
  - `cold-start-root` — только с одной причиной: `context-budget`, `capability-missing`,
    `owner-pause-no-resume`, `whole-plan-independent-audit` или `design-root-terminal`.
    `design-root-terminal` сохранён для старых handoff. После design используй
    `scope-complete` / `continue-root`, если нет настоящей границы новой сессии;
    рекомендация сама по себе не разрешает исполнение successor.
    Terminal `task:plan-audit` does not select Context by command name; use its persisted
    `plan_continuity` decision.
- **owner-run step** → «ЗАПУСК ВРУЧНУЮ» form — the rule lives in SKILL section 8 (single SSOT).
  Reminder: `Model class` = the Routing class, the fenced block is REQUIRED and carries a
  **BARE item prompt** (or a `/model`+`/effort`+`/task:plan-run` sequence)
  instead of an invocation, `Context` = `continue-root`, если нет фактической hard boundary.
- **Форма «ОЖИДАНИЕ: `<условие>` → `<целевая форма>`» (§8, D8)** — шаг реален, но неисполним
  сейчас (time-gate/накопление данных/кросс-план-гейт не терминален; НЕ дефект `🔴`, НЕ терминал
  «план закрыт»). Правило целиком в SKILL разделе 8; здесь напоминание: условие СТРУКТУРНО
  (дата/гейт), первая строка code-block'а — **guard `# НЕ раньше: <условие>`**, `Model class`/`Effort`/
  `Context` — **целевого шага**. Прозаическую оговорку в объявлении не писать (`plan-lint` метит C2).
- `plan-lint` проверяет semantic `Next`, таблицу с `| Model class |` и fenced block ниже;
  legacy-строка `| Команда |` принимается только для обратной совместимости старых планов.
