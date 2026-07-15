# HANDOFF — 2026-07-15 — after P5.2

**Next:** «ЗАПУСК ВРУЧНУЮ: opus/high» — P5.3 (Exec=manual, Routing §3: opus/high, синтез ROI =
архитектурное решение, вне пина `plan-exec`). Либо: `/model opus` + `/effort high` +
`/task:plan-run 2026.07.15-TELEMETRY-OPT P5.3` (D18).

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — синтез ROI-backlog + рекомендация приоритизации (Routing §3) |
| Context | continue (/clear) — ручной item |
| Суть | Свести кандидатов P5.1+P5.2 в ROI-ранжированный backlog + рекомендация Owner по P2–P4/P6+ |

```
Исполни P5.3 мастер-плана plans/2026.07.15-TELEMETRY-OPT (репо swissknifeman) строго по ТЗ
phases/P5.md:

**Intent:** Свести кандидатов P5.1 (внутренние) + P5.2 (внешние) в единый ранжированный по ROI
backlog (findings/P5-optimization-backlog.md): каждый рычаг — экономия · стоимость · риск ·
вердикт; вывести рекомендацию Owner: переупорядочить P2–P4 по ROI и/или породить новые фазы P6+.

**Scope Included:** объединение двух findings в один backlog с колонками рычаг/экономия/
стоимость/риск/вердикт/источник; ROI-сортировка; рекомендация по последовательности P2–P4 и
кандидаты на P6+; фиксация в plan.md (D-запись) при принятии Owner.

**Scope Excluded:** реализация рычагов (будущие фазы); сбор данных (P5.1/P5.2 закрыты);
авто-переупорядочивание фаз без Owner-approve.

**Required Reads:** 1) plans/2026.07.15-TELEMETRY-OPT/findings/P5-internal-budget-audit.md
2) plans/2026.07.15-TELEMETRY-OPT/findings/P5-external-bestpractices.md
3) plans/2026.07.15-TELEMETRY-OPT/plan.md (§4 Status Board, §5 D-лог)

**Implementation Rules:** ROI = оценённая экономия / стоимость внедрения — обе величины из
findings, не из воздуха; кандидат без числа с обеих сторон помечается «нужен замер», не
ранжируется вслепую; переупорядочивание P2–P4 / новые фазы — только РЕКОМЕНДАЦИЯ, применяет
Owner (авто-правка Status Board без approve запрещена).

**Code Guidance:** Synthesis-item, кода нет. Если P5.1 или P5.2 неполны — backlog помечает
пробелы явно, НЕ доранжировывает гипотезами. Рекомендация обязана опираться на числа backlog.
Запрещено помечать 🟢 при неоформленной рекомендации Owner.

**Validation:** findings/P5-optimization-backlog.md существует, ROI-ранжирован, каждый рычаг со
ссылкой на источник-findings; содержит явную секцию «Рекомендация приоритизации P2–P4 / P6+»;
пробелы данных отмечены.

**Files:** plans/2026.07.15-TELEMETRY-OPT/findings/P5-optimization-backlog.md (создать) ·
plan.md (D-запись/Update Log при approve)

После работы — обязательное закрытие item'а по протоколу plan-exec (Status/Completion Notes/
Pending Work/Known Deviations, item-коммит по Files выше, bookkeeping-коммит, перезапись
handoff.md, plan-lint.py). Закрытие P5.3 делает фазу P5 терминальной — заполнить Phase Handoff
в phases/P5.md и Status Board. Model/effort сессии — opus/high, НЕ переключай на sonnet/medium.
```

**Done:** P5.2 закрыт (item-коммит 77829c4): внешний RAG-развед токен-экономии 2026 — 6
последовательных `perplexity-web`-запросов (context7 — quota-промах, штатный фолбэк), 8
кандидатов C1–C8 в `findings/P5-external-bestpractices.md`, все RAG-маркированы. Adopt-кандидаты:
C4 (потолок+truncation-receipt в ответах maind MCP-тулов) · C5 (прополка MCP-серверов + deferred
tool-loading, пара к К1 из P5.1; `ENABLE_TOOL_SEARCH` — `[UNVERIFIED]`, нужна пред-проверка по
first-party доке). Reference: C1 prompt-cache (кэш уже здоров) · C2 compaction (уже канон
`context-economy`) · C3 sub-agent isolation · C6 tiered routing (валидирует D8/D9). Skip: C7
cascade-router · C8 vector-store память — обе строками в `docs/rejected-optimizations.md`;
+1 строка в `docs/reference.md`.

**Remaining:** P5.3 (синтез ROI-backlog, manual/opus/high, ⬜) — оба Required Reads готовы
(P5.1 ∥ P5.2 закрыты), можно исполнять сейчас; закрывает фазу P5. P1 терминальна (🟠),
P2/P3/P4 терминальны (🟢).

**Sources of truth:** `findings/P5-internal-budget-audit.md` (P5.1: 3 кандидата К1–К3 с
измеренным резидентом) · `findings/P5-external-bestpractices.md` (P5.2: C1–C8 с вердиктами) ·
`phases/P5.md` (ТЗ P5.3 + Completion Notes P5.1/P5.2) · `plan.md` (§3 Routing, §4 Phase Index,
§5 D-лог) · `docs/reference.md` / `docs/rejected-optimizations.md` (внешний провенанс P5.2).

**Open risks:** OQ-5 (Owner-решение по осям B/C permission-friction) и OQ-4 (research
opus→sonnet) остаются Decision pending, вне P5. `ENABLE_TOOL_SEARCH` (C5) — [UNVERIFIED],
внедрение без пред-проверки по first-party доке запрещено. Посторонний дифф в дереве:
untracked `plans/2026.07.15-PLANFLOW-UX/` — не тронут этим item'ом, владелец работает
параллельно — не коммитить/не ревертить без явного запроса.

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: пред-проверка `ENABLE_TOOL_SEARCH` (C5) и замер размеров ответов maind MCP-тулов
  (C4) — на фазе реализации / ROI в P5.3.
- open_questions: **OQ-5** — Decision pending (владелец Dmitry Vostrikov). **OQ-4** — Decision
  pending (research opus→sonnet). OQ-1/OQ-2/OQ-3 Resolved.
