# 2026.07.15-TOKEN-ECON-P6 — Дожим ROI-backlog токен-экономии (P6+ из TELEMETRY-OPT)

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.07.15-TOKEN-ECON-P6 |
| Title | Дожим ROI-backlog токен-экономии: MCP-прополка, сжатие описаний, maind-тримминг + owner-решения |
| Version | 0.3.0 |
| Status | 🟠 Done with deviations |
| superseded-by | 2026.07.25-ECO-OPT |
| Document Type | Executable Master Plan |
| Authoring Model | opus |
| Last Updated | 2026-07-15 (P6.1 закрыт) |
| Repository | swissknifeman |
| Related Packages | skiller (budget/registry, description-сжатие), harness (mcp-advisor guidance, ENABLE_TOOL_SEARCH пред-проверка), maind (tool-result trimming), task (research routing) |
| Execution Mode | phase-first |
| Target Operator Models | sonnet (exec) · opus (owner-решения/дизайн) |
| Approval Owner | Dmitry Vostrikov |
| Home | repo:/home/vostrikov/projects/packages/swissknifeman |
| Paused By | 2026.07.18-FOREMAN, 2026-07-18 |

## 1. Context

Продолжение закрытого `2026.07.15-TELEMETRY-OPT` (архив: `plans/archive/2026.07.15-TELEMETRY-OPT/`).
Его фаза P5 (discovery) синтезировала ROI-ранжированный backlog рычагов токен-экономии
(`findings/P5-optimization-backlog.md`) и оставила две пары Decision-pending вопросов
(`open-questions.md` OQ-4, OQ-5) — Owner решил не продолжать этими item'ами старый план, а
завести отдельный. Этот план добивает четыре форвард-рекомендации:

1. **P6 — MCP-поверхность (L1, наивысший измеренный ROI):** прополка резидентных MCP-серверов
   на жирных проектах (измерено: до 10650 ток / 35% резидента dterema/app) + GATED-подпункт L3
   (`ENABLE_TOOL_SEARCH`, `[UNVERIFIED]` — пред-проверка по first-party доке ОБЯЗАТЕЛЬНА до
   внедрения).
2. **P7 — Сжатие ⊕always-`description` топ-скиллов (L2):** сначала замер множителя N (число
   проектов-подписчиков на бакеты `architect`/`system`), затем сжатие ~30% с сохранением триггеров.
3. **P8 — Tool-result trimming в maind MCP (L4):** сначала замер фактических размеров ответов
   `maind_memory_recall`/`maind_graph_*`, затем потолок + `truncated`/PARTIAL-receipt при
   подтверждённом жире.
4. **P9 — Owner-решения из TELEMETRY-OPT (OQ-4, OQ-5):** A/B-вердикт по `task:research`
   opus→sonnet downgrade (OQ-4) и риск-аппетит по P4 protection-surface осям B/C (OQ-5) —
   решения владельца, не переносятся автоматически.

Это forward-looking backlog, не переупорядочивание завершённой работы (P1–P5 TELEMETRY-OPT
терминальны). L5 (CLAUDE.md-тримминг на memster/dterema) и C7/C8 (skip) в этот план НЕ входят —
вне scope монорепо swissknifeman (см. `docs/rejected-optimizations.md` и field-feedback-loop).

## 2. Execution Rules

- Один item за раз; статус обновляется В ПЛАНЕ до завершения работы.
- Статусы — 6 канонических строк байт-в-байт (plan-protocol §5).
- **stdlib-only** во всех python-правках (harness/maind/skiller) — жёстко, без pip.
- Замер-item'ы (P7.1, P8.1) — числа берутся из фактических источников (budget.py/скрипт замера),
  не из оценок; результат — предпосылка для follow-up item'а, не решение вслепую.
- L3 (`ENABLE_TOOL_SEARCH`, P6.2) — **GATED**: пред-проверка по first-party доке Claude Code
  обязательна ДО любого harness-пресета; при не-подтверждении — `⛔ Skipped by decision`, не
  импровизировать вокруг блога.
- П9-items (owner-решения) — `Exec = manual`, без plan-exec: решение фиксируется в D-логе ПОСЛЕ
  ответа Owner, не выводится агентом за него.
- План разошёлся с кодом → не импровизировать, эскалировать (plan-protocol §10).
- После закрытия item/фазы — перезаписать `handoff.md`; после правок скиллов — `skiller registry`.

## 3. Routing

<Отклонения от SSOT-матрицы §9.>

| Items | Model/effort | Exec | Почему |
|:--|:--|:--|:--|
| P6.1 | sonnet/medium | plan-exec | repo-grounded инвентаризация MCP-серверов по проектам + guidance-правка — детерминированная Validation |
| P6.2 | opus/high | manual | пред-проверка `[UNVERIFIED]`-флага по first-party доке = внешний факт, RAG-лестница context7→perplexity обязательна; effort high — решение GATED |
| P7.1 | sonnet/medium | plan-exec | repo-grounded замер N (skills-lock.json/topology.json по подписчикам) — детерминированный |
| P7.2 | sonnet/medium | plan-exec | правка `SKILL.ru.md`→регенерация EN + `skiller registry` — детерминированные гейты |
| P8.1 | sonnet/medium | plan-exec | repo-grounded замер размеров ответов maind MCP-тулов на живых вызовах |
| P8.2 | sonnet/medium | plan-exec | stdlib-only код Python-сервера maind (trimming + PARTIAL-receipt) — детерминированная Validation |
| P9.1 | opus/high | manual | A/B-вердикт `task:research` opus→sonnet — архитектурное owner-решение, RAG на model-capabilities |
| P9.2 | opus/high | manual | риск-аппетит protection-surface (permissions/auto-approve) — Owner-gated, вне plan-exec |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P6 | MCP-поверхность: прополка резидентных серверов (L1) + ENABLE_TOOL_SEARCH gated (L3) | 1/2 | 🟠 Done with deviations |
| P7 | Сжатие ⊕always-description топ-скиллов (L2) | 0/2 | ⛔ Skipped by decision |
| P8 | Tool-result trimming в maind MCP (L4) | 0/2 | ⛔ Skipped by decision |
| P9 | Owner-решения: research routing (OQ-4) + permission-friction protection-surface (OQ-5) | 0/2 | ⛔ Skipped by decision |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-07-15 | Дом плана — репо swissknifeman (`plans/`); продолжение backlog `2026.07.15-TELEMETRY-OPT` P5.3 отдельным планом, не реопеном закрытого | Owner решил не реопенить терминальный TELEMETRY-OPT — форвард-рекомендация P6+ была явно «применяет Owner», approve получен постфактум созданием этого плана. RAG:— (repo-grounded: `plans/archive/2026.07.15-TELEMETRY-OPT/findings/P5-optimization-backlog.md` секция «Рекомендация приоритизации», решение Owner в сессии) |
| D2 | 2026-07-15 | Порядок фаз P6→P7→P8→P9 по ROI backlog'а (P6 наивысший измеренный ROI+LOW-стоимость, P7 множитель требует замера N, P8 требует замера размеров прежде ранжирования, P9 — чистые owner-решения без кода) | Дословно порядок рекомендации P5.3: «P6 = единственный рычаг с измеренной экономией И LOW-стоимостью → первый; P7 = LOW-стоимость, но множитель требует замера N → второй; P8 = MED-стоимость и экономия ещё не оценена → третий». P9 добавлена последней — чистые decision-item'ы, не блокируют код-фазы. RAG:— (repo-grounded: `findings/P5-optimization-backlog.md` секция «Рекомендация приоритизации P2–P4 / P6+») |
| D3 | 2026-07-15 | L5 (CLAUDE.md-тримминг на внешних проектах memster/dterema) в этот план НЕ входит | Явно вне scope монорепо swissknifeman по вердикту P5.3 — рычаг применяют владельцы тех репо через field-feedback-loop/онбординг-дисциплину, не фаза кода этого плана. RAG:— (repo-grounded: `findings/P5-optimization-backlog.md` секция «Вне фаз этого плана») |
| D4 | 2026-07-15 | Дизайн-RAG P6: `ENABLE_TOOL_SEARCH` — реальный first-party флаг, И deferred MCP-loading ВКЛЮЧЁН ПО УМОЛЧАНИЮ для first-party Claude Code CLI (наш сетап). Следствие: L3 (P6.2) вероятно moot, ликвидный исход — `⛔ Skipped`; L1 (P6.1) премиса «10650/35% резидента» ослаблена (budget.py моделирует eager-load, tool-search defer'ит схемы) — прополку ранжировать по ЧЕСТНОЙ сниженной оценке. Снимает `[UNVERIFIED]`-флаг L3 на уровне «существование», гейт P6.2 смещается на first-party подтверждение семантики | RAG:✅ 2026-07-15 (perplexity-web ×2 → `code.claude.com/docs/en/agent-sdk/tool-search`, `code.claude.com/docs/*/env-vars`; корроборация ЖИВОЙ сессией — deferred-tools + `ToolSearch` активны; context7 quota-exhausted, fallback). Полный финдинг — `findings/P6-tool-search-precheck.md` |
| D5 | 2026-07-15 | L1-рычаг (P6.1) в scope монорепо = guidance-правка тела скилла `mcp-advisor` (CORE, on-trigger в каждый проект) + инвентарь-финдинг; правки чужих `.mcp.json` (внешние проекты) — вне scope | Зеркалит границу D3/L5: swissknifeman-код не редактирует конфиги внешних репо; рычаг = раздаваемая guidance + измеренная инвентаризация, применяют владельцы. RAG:— (repo-grounded: `packages/skiller/CLAUDE.md` CORE-политика, `config.py` `CORE_SKILLS`) |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-15 | plan-design/opus | План создан как продолжение backlog `2026.07.15-TELEMETRY-OPT` P5.3 (D1); P6–P9 скелеты, Routing §3 покрывает все items. ACTIVE → 2026.07.15-TOKEN-ECON-P6 |
| 2026-07-15 | plan-design/opus | P6 детализирована (2 items, DoR-пройден); дизайн-RAG снял `[UNVERIFIED]` L3 → D4 (tool-search default-on first-party, L3 вероятно moot), D5 (L1 = guidance-only scope). Финдинг `findings/P6-tool-search-precheck.md`. Version 0.1.0→0.2.0 |
| 2026-07-15 | plan-exec/sonnet | P6.1 закрыт: инвентарь 22 проектов + guidance-правка `mcp-advisor` — детали см. `phases/P6.md` P6.1 Completion Notes |
| 2026-07-18 | plan-design/fable | ACTIVE перехвачен планом 2026.07.18-FOREMAN (Paused By проставлен); план не закрыт, резюм — после FOREMAN или по решению владельца |
| 2026-07-25 | plan-design/Claude Fable 5 | План закрыт переносом (директива владельца): supersedes → 2026.07.25-ECO-OPT (P6.2→P1.1, P7→P3.1, P8→P3.2, P9→P3.3); статус 🟠 Done with deviations (P6 1/2, P7–P9 не исполнялись здесь); в архив |
