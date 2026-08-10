# 2026.07.15-TOKEN-ECON-P6 — Дожим ROI-backlog токен-экономии (P6+ из TELEMETRY-OPT)

## Identity
- Plan ID: 2026.07.15-TOKEN-ECON-P6
- Title: Дожим ROI-backlog токен-экономии: MCP-прополка, сжатие описаний, maind-тримминг + owner-решения
- Document Type: Executable Master Plan
- Repository: swissknifeman
- Home: repo:/home/vostrikov/projects/packages/swissknifeman

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
