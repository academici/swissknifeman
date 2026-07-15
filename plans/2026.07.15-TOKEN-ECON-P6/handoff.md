# HANDOFF — 2026-07-15 — after P6.1

**Next:** «ЗАПУСК ВРУЧНУЮ: opus/high» — P6.2 (`Exec = manual`, GATED)

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — GATED-решение, RAG-лестница по first-party доке обязательна |
| Context | continue (/clear) — ручной item |
| Суть | подтвердить `ENABLE_TOOL_SEARCH`/deferred MCP-loading НАПРЯМУЮ по `code.claude.com/docs` (не по дизайн-финдингу/блогу), отработать ветку A/B/C, закрыть P6.2 |

```
Плановый item P6.2 (2026.07.15-TOKEN-ECON-P6) — «Пред-проверка ENABLE_TOOL_SEARCH по first-party доке (L3, GATED)».

Intent: Подтвердить семантику `ENABLE_TOOL_SEARCH` НАПРЯМУЮ по first-party доке (`code.claude.com/docs`),
а НЕ по блогу/reddit/дизайн-финдингу; определить, оправдано ли ЛЮБОЕ harness-действие, и отработать ветку:
(A) уже default-on для first-party CLI → `⛔ Skipped by decision (уже активно)` + опц. заметка в
`mcp-advisor`; (B) в каком-то сетапе экосистемы off/требует включения → спроектировать harness-пресет/
guidance с цитатой доки; (C) не подтверждается first-party → `⛔ Skipped`, БЕЗ импровизации вокруг блога.

Why: L3 нёс `[UNVERIFIED]` (единственный источник — блог paddo.dev). Дизайн-RAG (`findings/P6-tool-search-precheck.md`)
сильно указывает: флаг РЕАЛЕН first-party И default-on для first-party CLI → пресет вероятно moot. Но
GATED-рычаг требует подтверждения по first-party доке ДО любой правки harness; слепое включение по
блогу = `[POSSIBLE-DEFECT]`.

Scope Included: RAG-верификация по лестнице (context7 Claude Code → perplexity-web → WebSearch),
приоритет — first-party `code.claude.com/docs` (env-vars + agent-sdk/tool-search страницы); фиксация
вердикта в `## 5. Decision Log` плана + дополнение `findings/P6-tool-search-precheck.md`; исполнение
ветки A/B/C.

Scope Excluded: любой harness-пресет на evidence блога/community/дизайн-финдинга БЕЗ first-party
подтверждения; глобальное включение флага без Owner-sign-off; правки L1 (P6.1, уже закрыт); переоценка
`budget.py`-модели (follow-up-кандидат из P6.1, не здесь).

Inputs: `findings/P6-tool-search-precheck.md` (дизайн-RAG, вердикт + остаточный риск + URL-источники);
`plans/archive/2026.07.15-TELEMETRY-OPT/findings/P5-optimization-backlog.md` (строка L3, `[UNVERIFIED]`-
происхождение).

Files: `plans/2026.07.15-TOKEN-ECON-P6/findings/P6-tool-search-precheck.md` (дополнение — вердикт
first-party); `plans/2026.07.15-TOKEN-ECON-P6/plan.md` (§5 Decision Log — D-запись вердикта); при ветке
B — `packages/harness/configs/claude-code/` (пресет) + возможно `mcp-advisor/SKILL.ru.md` (заметка); при
ветке A/C — только статус/D-лог.

Required Reads: (1) `findings/P6-tool-search-precheck.md`; (2) `plans/archive/2026.07.15-TELEMETRY-OPT/findings/P5-optimization-backlog.md`
(строка L3); (3) скилл `verify-claims` (RAG-лестница, порог доверия); (4) `packages/harness/CLAUDE.md`
(если ветка B — куда ляжет пресет).

Implementation Rules: RAG-лестница обязательна, гейт — ТОЛЬКО first-party (context7 может быть
quota-exhausted — тогда perplexity-web+WebSearch, но вердикт «делать пресет» опирается на
`code.claude.com`, не на community). Вердикт → D-запись в plan.md ПОСЛЕ верификации. `Exec = manual`
(opus) — не plan-exec, не автоматизируется. GATED: не подтверждено first-party → `⛔ Skipped by decision`,
не импровизировать.

Code Guidance: GATED-смещение: при неопределённости — дефолт `⛔ Skipped`, не «на всякий случай включим».
Не собирать пресет вокруг блога/reddit — только first-party URL. If-then: ветка B (пресет реально нужен)
добавляет always-on поведение → прогнать `skiller budget --first-turn` гейт И эскалировать Owner любую
смену глобального поведения (D-запись после approve, не за владельца). Честность: если вердикт = «moot,
уже default-on» — так и записать (`⛔ Skipped`, экономии рычага нет). `[POSSIBLE-DEFECT]` сохраняется при
любом внедрении без first-party подтверждения.

Validation: вердикт зафиксирован D-записью в `plan.md` §5 + дополнением `findings/P6-tool-search-precheck.md`
(first-party URL + дата + A/B/C); ветка A/C → статус item `⛔ Skipped by decision` с цитируемой причиной,
harness не тронут; ветка B → `bash packages/harness/scripts/validate.sh` зелёный + `skiller budget --first-turn`
гейт пройден + пресет цитирует first-party URL. Прогон `plan-lint` без ERROR.

После верификации — закрой P6.1→P6.2 топологией плана (Phase Status, Phase Index, handoff.md,
plan-lint --baseline HEAD).
```

**Done:** P6.1 (plan-exec/sonnet) закрыт — инвентарь 22 уникальных проектов (`~/.swissknifeman/projects.json`
дедуп) через `budget.py::_measure_mcp`, anti-pattern карты (`memory`/`filesystem` generic) не найдены ни
у кого, явных «сервер без сигнала» кандидатов нет; сверка модели с tool-search default-on (D4) — eager-
число `_measure_mcp` есть потолок, не факт резидента; guidance `mcp-advisor` дополнен разделом «Прополка
резидентного MCP» (0.1.0→0.2.0), `SKILL.md` регенерирован, `skiller registry`/`check-translations.sh`
зелёные. Item-коммит `e265153`.

**Remaining:** P6.2 (manual, opus — GATED). Затем детализация P7→P8→P9 (`/task:plan-design <ID> Pn`) и их
исполнение.

**Sources of truth:** `phases/P6.md` (ТЗ items, P6.1 Completion Notes) · `findings/P6-mcp-surface-inventory.md`
(инвентарь + сверка модели, P6.1) · `findings/P6-tool-search-precheck.md` (дизайн-RAG, tool-search
default-on) · `plan.md` §5 (D1–D5) · `plans/archive/2026.07.15-TELEMETRY-OPT/findings/P5-*` (числа
backlog К1 · происхождение L3).

**Open risks:** P6.2 — GATED: harness-действие только по first-party доке `code.claude.com`, не по
блогу/reddit; при неопределённости — `⛔ Skipped`; слепое включение = `[POSSIBLE-DEFECT]`. P9 — чистые
owner-решения, не закрываются plan-exec'ом. P6.1 follow-up (переоценка `budget.py`-модели под
deferred-loading, расширение карты `mcp-advisor` серверами вне 9 канонических: `serena` и др.) —
не закрыт, зафиксирован кандидатом в `findings/P6-mcp-surface-inventory.md`.

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: L5 (CLAUDE.md-тримминг внешних проектов) — вне scope (D3). Переоценка `budget.py`-MCP-модели
  под tool-search и расширение карты `mcp-advisor` — follow-up-кандидаты из P6.1 (не item этого плана,
  отдельная задача/план).
- open_questions: OQ-4, OQ-5 → items P9.1/P9.2 (решаются В плане).
