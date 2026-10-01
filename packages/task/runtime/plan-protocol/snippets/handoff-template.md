# Шаблон handoff.md — rolling-указатель plans/<PLAN-ID>/handoff.md

Перезаписывается ЦЕЛИКОМ при каждом закрытии item/фазы (история — в git).
Ключи блока Workarounds/Deferred/Open questions совпадают с run-report
`devloop{workarounds,deferred,open_questions}` — сверяемость с телеметрией.

**Заголовок** — две формы (иная = ERROR линтера; канон — SKILL §8):

| Форма заголовка | Когда |
|:--|:--|
| `# HANDOFF — <YYYY-MM-DD> — after Pn.m` | закрыт item |
| `# HANDOFF — <YYYY-MM-DD> — after Pn` | закрыта/проаудирована/ре-дизайнена ФАЗА — шаг без «последнего закрытого item'а» как адресата |

**Поле `Context`** для layout v2 — `continue-root` · `isolated-child-return` ·
`cold-start-root`. Последнее требует reason из закрытого enum:
`context-budget` · `capability-missing` · `owner-pause-no-resume` ·
`whole-plan-independent-audit` · `design-root-terminal`.
`design-root-terminal` сохранён только для старых handoff. Завершённый design использует
`scope-complete` / `continue-root`; рекомендация не разрешает исполнение. После terminal `task:plan-audit` Context
определяет сохранённое решение `plan_continuity`, а не имя команды.

Runnable Next для фактического successor обязан нести launch-block (полная форма и правила cold-start —
`snippets/launch-block-template.md`, SKILL раздел 8): таблица параметров запуска
+ provider-rendered invocation одним code-block. `plan-lint` проверяет их наличие.
Для execution Next таблица всегда несёт `Batch` из Routing, а команда — весь оставшийся
остаток группы. Для `recommended:` это рекомендация, допускающая ready subset; исторические
и `required:` группы сохраняют adjacent suffix. Одиночный запуск помечается `Batch: solo`. Для иных Next — `Batch: n/a`.

**Формы `Next`** — закрытый enum (иная форма = ERROR линтера; канон — SKILL §8):

| Форма Next | Когда |
|:--|:--|
| `run-items: task:plan-run <ID> Pn.a[-Pn.b]` | next item(s) detailed, Exec = run (§9); legacy spelling `exec-items: task:plan-exec` stays readable |
| `audit-design: task:plan-audit <ID> design` | pre-exec аудит дизайна |
| `design-phase: task:plan-design <ID> Pn` | следующая фаза — скелет |
| `design-item: task:plan-design <ID> Pn.m` | item эскалирован (🔴) либо требует ре-дизайна |
| `design-finish: task:plan-design <ID> finish` | reconciliation полностью детализированного дизайна |
| `design-roadmap: task:plan-design <ID> roadmap` | обновить execution map без правки ТЗ |
| `audit-phase: task:plan-audit <ID> Pn` | есть свежий owner-bound `audit-admission/v2` на residual-risk question/candidate/run |
| `close: task:plan-close <ID> Pn[.m]` | только явно запрошенная standalone reconciliation; не handoff текущего результата |
| `archive: task:plan-close archive <ID>` | план терминален целиком |
| `terminal: план закрыт` | все items терминальны, следующий шаг вне протокола |
| `manual: <model-class/effort>` | owner-run step with no command — launch-block carries the route and a BARE item prompt |
| `waiting: <условие> → <целевая semantic форма>` | шаг реален, но неисполним сейчас — launch-block несёт целевой carrier с guard-строкой `# НЕ раньше:` |

Historical `/task:…` declarations remain compatibility inputs. New plans write the semantic
form above; provider renderers emit Claude `/task:…` or Codex `$ task:…` without changing payload.
`plan-run` сам закрывает GREEN item и eligible final-item phase; handoff строится после
closure и не может повторять текущий item или запускать `plan-close` для него.

Форма «ЗАПУСК ВРУЧНУЮ» (owner-run step outside the command surface):

`````markdown
**Next:** manual: frontier/high — Pn.m (owner-run; no Task command carries it)

| Параметр | Значение |
|:--|:--|
| Batch | <Batch ID / solo> |
| Model class | frontier |
| Effort | high — <почему high+ MANDATORY по §9> |
| Capabilities | — |
| Context | continue-root |
| Суть | <1 строка> |

````
<ГОЛЫЙ ПРОМПТ item'а — не slash-команда: что прочитать, что сделать, как закрыть>
````
`````

Форма «ОЖИДАНИЕ» (шаг реален, но неисполним сейчас — time-gate/накопление данных/гейт не
терминален; условие структурно, launch-block несёт целевую команду с guard-строкой):

`````markdown
**Next:** waiting: ≥2026-07-16 (baseline usage-trend ≥1–2 недель) → run-items: task:plan-run <ID> P8.5

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Capabilities | — |
| Context | continue-root |
| Суть | <1 строка: что сделает целевой шаг по снятии гейта> |

````
# НЕ раньше: baseline usage-trend ≥1–2 недель, ≥2026-07-16
<provider-rendered invocation for `run-items: task:plan-run <ID> P8.5`>
````
`````

`````markdown
# HANDOFF — <YYYY-MM-DD> — after Pn.m

**Next:** run-items: task:plan-run <PLAN-ID> Pn.k

| Параметр | Значение |
|:--|:--|
| Model class | <economy / implementation / frontier> |
| Effort | <low / medium / high / xhigh> |
| Capabilities | <semantic capability IDs; `—` если дополнительных нет> |
| Context | <enum §6: continue-root · isolated-child-return · cold-start-root> |
| Суть | <1 строка: что делает следующий запуск> |

````
<provider-rendered invocation for `task:plan-run <PLAN-ID> Pn.k`; cold-start payload не менять>
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
