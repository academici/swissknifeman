# Шаблон handoff.md — rolling-указатель plans/<PLAN-ID>/handoff.md

Перезаписывается ЦЕЛИКОМ при каждом закрытии item/фазы (история — в git).
Ключи блока Workarounds/Deferred/Open questions совпадают с run-report
`devloop{workarounds,deferred,open_questions}` — сверяемость с телеметрией.

Next обязан нести launch-block (полная форма и правила cold-start —
`snippets/launch-block-template.md`, SKILL раздел 8): таблица параметров запуска
+ голая команда одним code-block. `plan-lint` проверяет их наличие (warning).

`````markdown
# HANDOFF — <YYYY-MM-DD> — after Pn.m

**Next:** /task:plan-exec <PLAN-ID> Pn.k

| Параметр | Значение |
|:--|:--|
| Model | <модель> |
| Thinking | <effort> |
| Context | <fresh session / continue> |
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
