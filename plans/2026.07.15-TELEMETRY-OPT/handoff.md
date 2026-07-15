# HANDOFF — 2026-07-15 — after P5.1

**Next:** «ЗАПУСК ВРУЧНУЮ: fable/medium» — P5.2 (Exec=manual, Routing §3: fable/medium,
внешний RAG-развед, вне пина `plan-exec`).

| Параметр | Значение |
|:--|:--|
| Model | fable |
| Thinking | medium — внешний RAG-развед, токен-дёшево (D1, Routing §3) |
| Context | continue (/clear) — ручной item |
| Суть | RAG-развед best-practices токен-экономии (perplexity-web/context7) + сверка с рамками swissknifeman |

```
Исполни P5.2 мастер-плана plans/2026.07.15-TELEMETRY-OPT (репо swissknifeman) строго по ТЗ
phases/P5.md:

**Intent:** Через perplexity-web/context7 собрать актуальные (2026) практики токен-экономии
агентных систем (структурирование prompt-cache и его TTL, context compaction/pruning, sub-agent
context isolation, tool-result trimming, model-routing по стоимости) и сверить каждую с
архитектурой swissknifeman; вывести кандидатов adopt/reference/skip.

**Scope Included:** RAG-запросы по перечню тем (дисциплина query-craft: версия/таймфрейм 2026/
формат); сверка каждой практики с рамками (stdlib-only, MCP-модель, кэш-профиль); вердикт
adopt/reference/skip; значимое → строка в docs/reference.md; отклонённое → docs/rejected-
optimizations.md.

**Scope Excluded:** реализация (будущие фазы); внутренние метрики (P5.1, уже закрыт —
findings/P5-internal-budget-audit.md); синтез (P5.3); WebSearch как первый движок (лестница
context7→perplexity→WebSearch).

**Required Reads:** 1) packages/skiller/skills/general/query-craft/SKILL.md 2) docs/reference.md
3) docs/rejected-optimizations.md 4) CLAUDE.md (раздел «Философия и рамки» + «Методология решений»)

**Implementation Rules:** RAG-лестница context7→perplexity-web→WebSearch (CLAUDE.md); каждый
несущий вердикт — `RAG:✅ <дата/источник>` либо `[UNVERIFIED]`; perplexity-web НЕ параллелить
(профиль-лок >120s) и не слать сверхдолгие search_deep (таймаут моста); практика, требующая
pip-рантайма — авто-skip (stdlib-only — жёстко).

**Validation:** findings/P5-external-bestpractices.md с ≥N кандидатами, каждый RAG-маркирован
(✅ с источником или [UNVERIFIED]); отклонённые отражены в docs/rejected-optimizations.md;
принятые значимые — в docs/reference.md.

**Files:** plans/2026.07.15-TELEMETRY-OPT/findings/P5-external-bestpractices.md (создать) ·
docs/reference.md (при adopt) · docs/rejected-optimizations.md (при skip)

После работы — обязательное закрытие item'а по протоколу plan-exec (Status/Completion Notes/
Pending Work/Known Deviations, item-коммит по Files выше, bookkeeping-коммит, перезапись
handoff.md, plan-lint.py). Model/effort сессии — fable/medium (уже установлены), НЕ переключай на
sonnet/medium.
```

**Done:** P5.1 закрыт: внутренний аудит always-on бюджета `skiller budget --first-turn` на 5
проектах разного стека (swissknifeman/vaulter/memster/dterema-app/erp-sdk) — 4/5 WARN (>10K ток).
Найдено 3 кандидата сжатия с измеренным резидентом: К1 MCP tool-defs (2250→10650 ток, 35% итога
на dterema/app, 7 резидентных серверов) · К2 CLAUDE.md сверх ≤200 строк (dterema/app 13535 ток,
memster 9055 ток) · К3 повторяющиеся ⊕always-описания скиллов across 3/5 проектов (множитель
N-подписчиков). Инструмент не сбоил ни на одном прогоне. Детали — `findings/
P5-internal-budget-audit.md`, `phases/P5.md` P5.1 Completion Notes.

**Remaining:** P5.2 (внешний RAG-развед, manual/fable/medium, ⬜) — независим от P5.1 (уже
закрыт), можно исполнять сейчас. P5.3 (синтез ROI-backlog, manual/opus/high) — ждёт P5.1 ∥ P5.2
(оба нужны как Required Reads). P1 терминальна (🟠), P2/P3/P4 терминальны (🟢).

**Sources of truth:** `findings/P5-internal-budget-audit.md` (P5.1 вердикт + 3 кандидата) ·
`phases/P5.md` (ТЗ P5.1/P5.2/P5.3 + Completion Notes) · `plan.md` (§3 Routing, §4 Phase Index) ·
`packages/skiller/lib/skiller/budget.py` (источник токен-математики).

**Open risks:** OQ-5 (Owner-решение по осям B/C permission-friction) и OQ-4 (research opus→sonnet)
остаются Decision pending, вне P5. Посторонний дифф в дереве на момент старта сессии:
`plans/2026.07.15-TELEMETRY-OPT/phases/P4.md` (modified) и untracked
`plans/2026.07.15-PLANFLOW-UX/` — не тронуты этим item'ом (не входят в Files P5.1), владелец
работает параллельно — не коммитить/не ревертить без явного запроса.

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: правки-сжатия по кандидатам К1/К2/К3 — measure-only item, реализация вне scope P5.1
  (будущие items по backlog P5.3).
- open_questions: **OQ-5** — Decision pending (владелец Dmitry Vostrikov). **OQ-4** — Decision
  pending (research opus→sonnet). OQ-1/OQ-2/OQ-3 Resolved.
