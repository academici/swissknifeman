# P6 — Пред-проверка `ENABLE_TOOL_SEARCH` / deferred MCP-loading (RAG-финдинг дизайна)

**Дата:** 2026-07-15 · **Кто:** plan-design/opus/high · **Тип:** RAG-верификация несущего факта фазы
(снимает `[UNVERIFIED]`-флаг L3 из `plans/archive/2026.07.15-TELEMETRY-OPT/findings/P5-optimization-backlog.md`).
**Ladder:** context7 (Claude Code) — **quota exceeded** (fallback) → **perplexity-web** (2 запроса) →
корроборация **живой сессией** (repo/env-grounded).

## Вопрос

L3-рычаг backlog'а предполагал harness-пресет, включающий `ENABLE_TOOL_SEARCH` (deferred загрузка
MCP tool-схем) ради экономии ~резидента MCP (до 10650 ток / 35% на dterema/app). Флаг нёс
`[UNVERIFIED]` (единственный источник — блог paddo.dev). Пред-проверка: **существует ли флаг
first-party И какой у него дефолт в нашем сетапе.**

## Вердикт (RAG:✅ 2026-07-15)

1. **`ENABLE_TOOL_SEARCH` — реальный first-party флаг Claude Code / Agent SDK.** Документирован:
   `code.claude.com/docs/en/agent-sdk/tool-search` (таблица значений, «Scale to many tools with
   tool search») и `code.claude.com/docs/*/env-vars` (env-var reference; читается на старте, задаётся
   shell-env ЛИБО `env`-блоком `.claude/settings.json`). Существование — подтверждено.
2. **Для first-party Claude Code CLI (наш сетап, без кастомного `ANTHROPIC_BASE_URL`) tool search /
   deferred MCP-loading ВКЛЮЧЁН ПО УМОЛЧАНИЮ.** Схемы MCP-тулов НЕ грузятся резидентно на старте —
   в контекст идут только summaries + per-server instructions; полные схемы подтягиваются
   `ToolSearch`-механизмом on-demand (3–5 тулов за вызов). `ENABLE_TOOL_SEARCH` нужен, чтобы
   ФОРСИРОВАТЬ/тюнить (`"1"`/`"true"`/`"auto:N"`) или ОТКЛЮЧИТЬ (`"false"`) — не «включить с нуля».
   Явно включать имеет смысл лишь за non-first-party base URL или при массе MCP-серверов.
3. **Корроборация живой сессией (env-grounded, сильнее блога):** ТЕКУЩАЯ сессия несёт
   system-reminder «Some tools are deferred… Use ToolSearch with query…» и рабочий инструмент
   `ToolSearch` — deferred-loading УЖЕ активен в проде экосистемы, не гипотеза.

## Импликации (reshape фазы — вносятся в D-лог плана)

- **L3 (P6.2) вероятно MOOT для first-party проектов:** нечего «включать» harness-пресетом —
  дефолт уже deferred. Ликвидный исход пред-проверки = `⛔ Skipped by decision (уже default-on)`
  + опц. заметка в `mcp-advisor`, а НЕ новый пресет. Ветка «делать пресет» остаётся только если
  first-party дока (не блог/reddit) покажет обратное ЛИБО в экосистеме есть проекты за прокси.
- **L1 (P6.1) премиса ослаблена:** `budget.py::_measure_mcp` (`budget.py:337-354`,
  `KNOWN_MCP_TOOLS`×150) моделирует EAGER-загрузку всех схем → «10650 ток / 35% dterema» это
  **потолок при выключенном tool search**, а не фактический first-turn резидент при дефолт-on.
  Реальный резидент MCP при tool search — summaries (кратно меньше). Прежде чем ранжировать
  прополку по «35%», P6.1 ОБЯЗАН сверить модель budget.py с реальностью tool-search (repo-grounded).
  Прополка не обнуляется (каждый сервер = summary + permissions + ToolSearch-поверхность), но её ROI
  ниже заявленного backlog'ом — честно зафиксировать.

## Доверие и остаточный риск

- Существование флага — **высокое доверие** (first-party URL + живая сессия).
- «Default-on для first-party CLI» и точная семантика значений (`auto:N`, поведение за прокси) —
  **среднее доверие**: часть источников — community (reddit/wmedia). Перед ЛЮБЫМ harness-действием
  P6.2 (opus/manual) обязан подтвердить по `code.claude.com/docs` напрямую (env-vars + tool-search
  страницы), не по этому финдингу и не по блогу — `[POSSIBLE-DEFECT]` при внедрении вслепую сохраняется.

## Источники

- perplexity-web синтез #1 → `code.claude.com/docs/en/agent-sdk/tool-search`, `code.claude.com/docs/it/env-vars`
- perplexity-web синтез #2 → community writeups (reddit r/ClaudeAI 1sy1m4x «tools are lazy-loaded»)
- env-grounded: system-reminder + `ToolSearch` в ТЕКУЩЕЙ сессии (deferred tools активны)
- repo-grounded: `packages/skiller/lib/skiller/budget.py:194-206,337-354` (eager-load MCP-модель)
