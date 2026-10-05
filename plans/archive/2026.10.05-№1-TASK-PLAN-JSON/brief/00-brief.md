# Brief — PLAN1 TASK-PLAN-JSON

## REPOSITORY-OWNER-MESSAGE (verbatim, 2026-10-05, `/task:plan-design`)

> Идея максимально стандартизировать план через json файлы.
> Для всех json файлов будет JsonSchema описания.
> Сейчас приходится менять план прямо в md файлах и разные провайдеры все-равно немного по своему делают, что неудобно.
> Я предлагаю либое взаимодействие с планом сделать через написанное апи на питоне, которое модифицирует json файлы.
> Нужно проанализировать планы проектов, чтобы выделить максимальную схему, например related_files, task_files (что нужно будет изменять в рамках задачи, но это не ограничение, а наводка), status, reviewer.
> Пункты фаз делить на отдельные файлы, чтобы агент не читал лишнюю инфу, а вообще желательно чтобы при старте задаче питон код автоматом ему подгатавливал всю инфу на основании json файлов, т.е. подгатавливал контект (или через слабую модель)
> Для brief, decisions и других свои схемы.
> Т.е. план ai-first, а для разработчика нужен по сути только
> handoff.md
> index.md
> open-questions.md
> plan.md
> roadmap.md
> status.md
> Они собираются на основании json файлов.
>
> Далее в json схеме фаз, унитывать максимум, типа rag_need, rag_status (comlete, fail)
> Если надо то в схеме указывать связанные пункты (например P1.2), связанные артифакты (через относительные пути), чтобы при старте задачи считывался весь полезный объем и агент знал что где лежит и как с этим работать.
> Еще желательно даже расширить, чтобы писались какие-то логи, о всех сложностях или отклонениях (но тут у меня слабое представление, нужно подумать, чтобы не перегружать агента)
> Еще была идея, оркестрации, например если выполняется codex, то его слабая модель (задается конфигом в skm) собирает контекст, как в видео https://www.youtube.com/shorts/ZweCNMdza8o,
> а написание конкретных кусков кода делегируется на другие (это надо продумать тоже, но главное чтобы хуже не стало)
> codex до сих пор начинает путить из-за перегруженных инструкций и я хз что с ним делать.
> Вообщем у тебя полная творческая свобода, план про принципу ai-first разаработка, а я только смотрю сгенерированную часть плана.
> Кстати для формирования md, можно использовать шаблоны, и куски шаблонов, например для строк таблиц и др. а питон будет на их основе формировать md файлы.
> Тебе надо продумать оптимальную структуру.
> А и еще, у нас есть какой-то plan_weight.py
> это ограничение мне кажется неразумным, и вообще посмотреть другие ограничение, которые потенциально не нужны.
>
> Никакого Legacy быть не должно. Текущуне планы по старому формату останутся, но ты напишешь md файл с инструкцией по миграции плана так чтобы его могла выполнить любая слабая модель, типа terra или grok 4.6
> как планы мигрируются, твою инструкцию можно будет удалить.
>
> При формировании плана дели его на разумные части, я хочу уложиться в 4-5 выполнений
>
> Используй perplexity для подкрепления и поиска решений, может он найдет что-то готовое, и можно будет адаптировать.

## REPOSITORY-OWNER-MESSAGE M2 (verbatim, 2026-10-05, during design)

> и еще у нас удалится много кода, который работал с md файлами, линтинг и т.д. А все проверки будут завязаны на json. И будут еще события когда после изменений, питон должен будет перегенерировать md файлы. И нужно чтобы для провайдеров были инструкции, что игнорировать в плане (сгенерированные файлы)

## REPOSITORY-OWNER-MESSAGE M3 (verbatim, 2026-10-05, during design)

> а еще идея, чтобы в json схеме предусмотреть оркестрацию, что внутри задачу можно поделить на куски и выдавать другим агентам

## REPOSITORY-OWNER-MESSAGE M4 (verbatim, 2026-10-05, during design)

> типа создавать в папке фазы, подпапку для пункта и в ней вести работу для субагентов

## Extracted requirements (normative)

| ID | Requirement | Owner in plan |
|:--|:--|:--|
| B1 | The plan is stored as JSON files; every JSON file has a JSON Schema | D1, P1.1 |
| B2 | Agents change the plan only through a Python API/CLI that edits JSON; never by hand | D1, P1.2, P3.1 |
| B3 | Maximal item schema from real plans: related files, task files (hint, not a limit), status, reviewer, related items (`P1.2`), artifacts by relative path, `rag_need`/`rag_status` | D1, P1.1 |
| B4 | One file per item so the agent reads nothing extra | D1, P1.1 |
| B5 | At start the API prepares the agent's whole context from JSON (optionally through a weak model) | P2.2, P4.1 |
| B6 | Separate schemas for brief, decisions and other carriers | P1.1 |
| B7 | Human views — exactly `handoff.md`, `index.md`, `open-questions.md`, `plan.md`, `roadmap.md`, `status.md` — are generated from JSON through templates and partials | D1, P1.3 |
| B8 | Sparse execution log of difficulties/deviations that does not overload the agent | D1, P2.1 |
| B9 | Orchestration: a weak model (configured in the package config) gathers context; code pieces may be delegated — must not make results worse | D3, P4 |
| B10 | Codex gets confused by overloaded instructions — commands must become short | D1, P3.1 |
| B11 | Remove `plan_weight.py` and review other unnecessary constraints | D2, P3.2 |
| B12 | No legacy code paths; old plans stay as files and are migrated by a Markdown instruction executable by a weak model (terra, grok 4.6); the instruction is deletable afterwards | D4, P3.1, P3.2 |
| B13 | 4–5 executions in total | Routing, `roadmap.md` |
| B14 | Use perplexity for supporting research | `research/01-rag.md` |
| B15 | All checks work on JSON; md-parsing/linting code is deleted (M2) | D1, D2, P1.2, P3.2 |
| B16 | Regeneration events: Python regenerates Markdown after every change, including out-of-band JSON edits (M2) | D1, P1.3, P3.1 |
| B17 | Provider instructions on what to ignore in a plan (generated files) (M2) | D1, P1.3, P3.1 |
| B18 | Orchestration in the schema: an item can be split into pieces handed to other agents (M3) | D3, P1.1, P4.2 |
| B19 | Sub-agent work lives in an item sub-folder inside the phase folder (M4) | D3, P1.1, P4.2 |

## Environment

- Repository: swissknifeman (monorepo); package `packages/task` (plugin-only, `lib/task/` stdlib-only).
- `plans/` is gitignored in this repository: plan bookkeeping is local, product commits contain only code/docs.
- Existing plans in sibling repositories (chatom, corex, azguard, vaulter) are not touched by this plan.
