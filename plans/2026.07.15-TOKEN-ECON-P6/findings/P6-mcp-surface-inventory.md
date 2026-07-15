# P6.1 — Инвентаризация резидентных MCP-серверов по проектам + сверка с tool-search

**Дата:** 2026-07-15 · **Кто:** plan-exec/sonnet/medium · **Тип:** repo-grounded инвентарь + сверка модели `budget.py`.

## Метод

`~/.swissknifeman/projects.json` несёт 31 запись `projects[].path`, дедуп по пути → **22 уникальных
проекта**. Для каждого — `budget.py::_measure_mcp(path)` (читает `<path>/.mcp.json`, суммирует
`KNOWN_MCP_TOOLS.get(server, FALLBACK_MCP_TOOLS) × TOKENS_PER_MCP_TOOL(150)`; неизвестный сервер →
`FALLBACK_MCP_TOOLS=5`). Все 22 пути существуют и читаемы — n/a-строк нет. Одноразовый скрипт обхода
(`/tmp/.../mcp_inventory.py`) — не коммитится (Implementation Rules).

## Таблица: проект → серверы → ток (eager-модель `_measure_mcp`)

| Проект | Серверов | Список | Ток (eager) |
|:--|--:|:--|--:|
| dterema/dterema | 8 | context7, dterema-nuxt-docs, laravel-boost, maind, naive-ui, perplexity-web, playwright, serena | 12450 |
| agelto/agelto | 6 | context7, laravel-boost, maind, perplexity-web, playwright, serena | 10950 |
| dterema/app | 7 | dterema-nuxt-docs, figma, maind, naive-ui, perplexity-web, playwright, serena | 10650 |
| sibintek/insiders | 5 | context7, laravel-boost, maind, perplexity-web, serena | 7800 |
| packages/vaulter | 4 | maind, perplexity-web, playwright, serena | 8400 |
| packages/chatom | 5 | context7, maind, perplexity-web, playwright, serena | 8700 |
| vintera/vintera | 6 | figma, maind, naive-ui, perplexity-web, playwright, vintera-nuxt-docs | 7650 |
| flexcrm | 4 | laravel-boost, maind, perplexity-web, serena | 7500 |
| Brain (vault) | 5 | context7, document-generator, github, maind, perplexity-web | 6300 |
| edufy | 5 | context7, document-generator, maind, perplexity-web, serena | 6300 |
| vintera/cms | 4 | boost, maind, perplexity-web, serena | 6000 |
| packages/perplexity-web-mcp | 4 | context7, maind, perplexity-web, serena | 5550 |
| memster | 3 | maind, perplexity-web, serena | 5250 |
| packages/azguard | 3 | maind, perplexity-web, serena | 5250 |
| packages/botkit | 3 | maind, perplexity-web, serena | 5250 |
| packages/corex | 3 | maind, perplexity-web, serena | 5250 |
| packages/loqum | 3 | context7, maind, perplexity-web | 2550 |
| axioma-studio | 2 | maind, perplexity-web | 2250 |
| diabox | 2 | maind, perplexity-web | 2250 |
| packages/erp-sdk | 2 | maind, perplexity-web | 2250 |
| packages/swissknifeman | 2 | maind, perplexity-web | 2250 |
| sibintek/sova | 1 | laravel-boost | 2250 |

Сырые данные (команда/скрипт воспроизводим по `budget.py::_measure_mcp`, without-args python one-liner
из `packages/skiller/lib` на `PYTHONPATH`).

## Наблюдения (маркировка кандидатов прополки)

- **Anti-pattern из карты `mcp-advisor` НЕ обнаружен ни в одном проекте:** generic `memory` (npx
  `server-memory`) и `filesystem` MCP отсутствуют во всех 22 `.mcp.json` — канон памяти (`maind`-хаб)
  соблюдается флотом без исключений.
- **`github` MCP** — только у Brain (vault, roль maintainer доков) — оправданный кейс по карте (не
  routine-review, конфиг вокруг доков). Остальные проекты используют `gh` CLI (не тянут MCP) — карта
  соблюдается.
- **`fetch`, `sequential-thinking`** — не подключены НИ У ОДНОГО проекта: подтверждает Implementation
  Rules-принцип «подключай по доказанной необходимости», не выявляет прополку.
- **Самые тяжёлые резиденты (по eager-модели):** `dterema/dterema` (12450, 8 серверов),
  `agelto/agelto` (10950, 6), `dterema/app` (10650, 7) — все три несут `playwright` + `serena` +
  доменные фронтенд-серверы (`naive-ui`/`dterema-nuxt-docs`/`figma`) одновременно; это frontend-heavy
  проекты, где карта `mcp-advisor` явно оправдывает `playwright` (UI/E2E) и стековые доп.-серверы —
  **не самопроизвольный bloat**, а следствие роли/стека. Прополку этих трёх точечно НЕ рекомендуем без
  сигнала владельца проекта (соответствует Scope Excluded — внешние `.mcp.json` не правим).
- **serena** присутствует в 15/22 проектов, но НЕ описан в карте `mcp-advisor` (таблица §«Карта
  серверов» покрывает context7/playwright/github/fetch/perplexity/sequential-thinking/filesystem/
  memory/maind — `serena`/граф кода и доменные докс-серверы туда не входят). Это документационный
  пробел карты, а не находка прополки конкретного проекта — правка Scope Excluded этого item'а
  (не «переписывать budget-математику»/не расширять карту в этом item'е); зафиксировано как follow-up
  ниже.
- **Итог:** явных кандидатов «сервер подключён без сигнала проекта» (тот класс, который карта
  `mcp-advisor` помечает «Не нужен когда…») по 22 проектам **не найдено** — экосистема уже держит
  дисциплину подбора. Рычаг L1 в этом item'е приземляется НЕ как «список серверов на отключение»
  (такого списка нет), а как усиление ГАЙДА/ритуала аудита (Scope Included п.3) + честная поправка
  премисы backlog'а (ниже).

## Сверка модели `budget.py::_measure_mcp` с реальностью tool-search (D4)

`_measure_mcp` (`budget.py:337-354`) — статичная EAGER-оценка: сумма `tool_count × 150` по всем
серверам `.mcp.json`, БЕЗ учёта того, что first-party Claude Code CLI держит tool search / deferred
MCP-loading **включённым по умолчанию** (`findings/P6-tool-search-precheck.md`, D4). Deferred-loading
означает: в system prompt резидентны **summaries + per-server instructions**, полные tool-схемы (те,
что `_measure_mcp` считает по 150 ток/шт.) подгружаются `ToolSearch` on-demand (3–5 тулов за вызов), не
все сразу.

**Вывод:** числа таблицы выше (2250…12450) — это **потолок при выключенном/недоступном tool search**,
НЕ фактический first-turn резидент типового прогона с default-on deferred loading. Реальный резидент
кратно меньше (summary на сервер, не полная схема каждого тула) — точная формула deferred-резидента
`budget.py` не моделирует (эта модель не переписывается в рамках этого item'а — Scope Excluded:
«изменение токен-математики `budget.py` — ОТДЕЛЬНЫЙ кандидат»). Прополка резидентного MCP как рычаг
**не обнуляется** (каждый сервер всё равно = summary-строка + permissions-поверхность + вход в
ToolSearch-каталог + Node/uvx-деп на диске), но её ROI **ниже**, чем заявлял backlog TELEMETRY-OPT
(«10650 ток / 35% резидента dterema/app» — та цифра для eager-режима, не факт при default-on
tool-search).

## Follow-up кандидаты (НЕ выполняются в этом item'е)

1. **Переоценка `budget.py::_measure_mcp` под deferred/tool-search-модель** (доб. поле «резидент при
   tool-search ≈ summary-оценка» рядом с eager-потолком) — материальное расхождение (>~2×) есть, но
   правка формулы вне Scope Included P6.1 (Code Guidance: «if-then… зафиксируй follow-up-кандидат... не
   переписывай budget-математику молча»). Кандидат для отдельного item'а/плана.
2. **Расширение карты `mcp-advisor` серверами вне текущей таблицы** (`serena`, доменные докс-серверы
   `*-nuxt-docs`, `naive-ui`, `figma`, `laravel-boost`/`boost`, `document-generator`) — карта сейчас
   покрывает только 9 канонических записей; 22-проектный инвентарь показал, что реальный флот
   регулярно несёт серверы вне карты. Не сделано здесь: расширение карты — самостоятельная content-
   правка (риск раздуть тело скилла без бюджет-гейта), не часть «прополка резидентного MCP».

## Guidance-правка (Scope Included п.3)

`mcp-advisor/SKILL.ru.md` дополнен подразделом «Прополка резидентного MCP» — ритуал аудита
(`skiller budget --first-turn` → строка MCP), правило «1–2 сервера на задачу», caveat про
tool-search (не заявлять экономию на eager-числе). `SKILL.md` регенерирован из RU, `skiller registry`
прогнан (см. Completion Notes item'а).
