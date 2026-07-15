# Шаблон handoff.md — rolling-указатель plans/<PLAN-ID>/handoff.md

Перезаписывается ЦЕЛИКОМ при каждом закрытии item/фазы (история — в git).
Ключи блока Workarounds/Deferred/Open questions совпадают с run-report
`devloop{workarounds,deferred,open_questions}` — сверяемость с телеметрией.

**Заголовок** — две формы (иная = ERROR линтера; канон — SKILL §8):

| Форма заголовка | Когда |
|:--|:--|
| `# HANDOFF — <YYYY-MM-DD> — after Pn.m` | закрыт item |
| `# HANDOFF — <YYYY-MM-DD> — after Pn` | закрыта/проаудирована/ре-дизайнена ФАЗА — шаг без «последнего закрытого item'а» как адресата |

**Поле `Context`** launch-block'а — закрытый enum трёх значений (SKILL §8): `continue
(/clear) — ручной item` · `NEW SESSION — Workflow-оркестрован` · `NEW SESSION —
шаг-не-item` (`plan-audit`/`plan-close`/`plan-design`). Статичное «рекомендован /clear»
независимо от типа следующего шага — запрещено.

Next обязан нести launch-block (полная форма и правила cold-start —
`snippets/launch-block-template.md`, SKILL раздел 8): таблица параметров запуска
+ голая команда одним code-block. `plan-lint` проверяет их наличие (warning).

**Формы `Next`** — закрытый enum (иная форма = ERROR линтера; канон — SKILL §8):

| Форма Next | Когда |
|:--|:--|
| `/task:plan-exec <ID> Pn.m` | следующий item детализирован, Exec = plan-exec (§9) |
| `/task:plan-design <ID> Pn` | следующая фаза — скелет |
| `/task:plan-design <ID> Pn.m` | item эскалирован (🔴) либо требует ре-дизайна |
| `/task:plan-audit <ID> Pn` | фаза Pn закрыта (терминальна) — аудит перед следующей |
| `/task:plan-close <ID> Pn[.m]` | items терминальны: закрыть фазу / сверить item |
| `/task:plan-close archive <ID>` | план терминален целиком |
| «план закрыт» | все items терминальны, следующий шаг вне протокола |
| «ЗАПУСК ВРУЧНУЮ: `<model/effort>`» | Exec = manual (§9): команды нет — launch-block несёт модель и ГОЛЫЙ ПРОМПТ item'а |
| «ОЖИДАНИЕ: `<условие>` → `<целевая форма>`» | шаг реален, но неисполним сейчас (time-gate/накопление данных/кросс-план-гейт не терминален) — launch-block несёт целевую команду с guard-строкой `# НЕ раньше:` (SKILL §8, D8) |

Форма «ЗАПУСК ВРУЧНУЮ» (item с Exec = manual — модель выше пина `plan-exec`):

`````markdown
**Next:** ЗАПУСК ВРУЧНУЮ: opus/high — Pn.m (§3 Routing: Exec = manual; `/task:plan-exec`
пинит sonnet/medium и по routing-гейту §9 обязан отказать)

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — <почему high+ MANDATORY по §9> |
| Context | continue (/clear) — ручной item |
| Суть | <1 строка> |

````
<ГОЛЫЙ ПРОМПТ item'а — не slash-команда: что прочитать, что сделать, как закрыть>
````
`````

Форма «ОЖИДАНИЕ» (шаг реален, но неисполним сейчас — time-gate/накопление данных/гейт не
терминален; условие структурно, launch-block несёт целевую команду с guard-строкой):

`````markdown
**Next:** ОЖИДАНИЕ: ≥2026-07-16 (baseline usage-trend ≥1–2 недель) → /task:plan-exec <ID> P8.5

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium |
| Context | continue (/clear) — ручной item |
| Суть | <1 строка: что сделает целевой шаг по снятии гейта> |

````
# НЕ раньше: baseline usage-trend ≥1–2 недель, ≥2026-07-16
/task:plan-exec <ID> P8.5 — <cold-start: пути входных доков + утверждение гейта>
````
`````

`````markdown
# HANDOFF — <YYYY-MM-DD> — after Pn.m

**Next:** /task:plan-exec <PLAN-ID> Pn.k

| Параметр | Значение |
|:--|:--|
| Model | <модель> |
| Thinking | <effort> |
| Context | <enum §8: continue (/clear) — ручной item · NEW SESSION — Workflow-оркестрован · NEW SESSION — шаг-не-item> |
| Суть | <1 строка: что делает следующий запуск> |

````
/task:plan-exec <PLAN-ID> Pn.k — <cold-start: пути входных доков + утверждение гейта, если гейтится>
````

**Done:** <что закрыто с прошлого handoff: items, фазы, решения>
**Remaining:** <что осталось до конца фазы/плана>
**Sources of truth:** plans/<PLAN-ID>/plan.md · plans/<PLAN-ID>/phases/Pn.md · <ключевые файлы кода>
**Open risks:** <открытые риски; «—» если нет>
**Workarounds/Deferred/Open questions:**
- workarounds: <обходки, принятые в ходе исполнения; «—» если нет>
- deferred: <осознанно отложенное; «—» если нет>
- open_questions: <вопросы, требующие решения человека/plan-design; «—» если нет>
`````
