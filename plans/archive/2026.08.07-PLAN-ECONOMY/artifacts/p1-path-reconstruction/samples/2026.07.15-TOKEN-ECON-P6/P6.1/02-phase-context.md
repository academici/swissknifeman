# P6 — MCP-поверхность: прополка резидентных серверов (L1) + ENABLE_TOOL_SEARCH gated (L3)

## Phase Context

Фаза добивает L1 (наивысший измеренный ROI backlog'а: до 10650 ток / 35% резидента dterema/app,
7 MCP-серверов) + L3 (`ENABLE_TOOL_SEARCH`, deferred MCP-loading) как GATED-подпункт. **Дизайн-RAG
переформатировал премису** (`findings/P6-tool-search-precheck.md`, RAG:✅ 2026-07-15): для
first-party Claude Code CLI — нашего сетапа — tool search / deferred MCP-loading **включён по
умолчанию** (доказано ЖИВОЙ сессией: deferred-tools + `ToolSearch` активны), значит MCP tool-схемы
НЕ резидентны первым ходом (грузятся summaries, полные схемы — on-demand). Следствия: (1) L3
(P6.2) вероятно **moot** — включать нечего, дефолт уже deferred → ликвидный исход = `⛔ Skipped`;
(2) L1 (P6.1) премиса ослаблена — `budget.py::_measure_mcp` моделирует EAGER-загрузку → «35%» это
потолок, не факт; прополка не обнуляется (каждый сервер = summary + permissions + ToolSearch-поверхность),
но ROI честно ниже backlog'а. Scope L1 в этом репо = guidance-правка `mcp-advisor` (CORE, on-trigger
в каждый проект) — **НЕ** правки чужих `.mcp.json` (внешние проекты — вне scope монорепо, как D3/L5).
P6.1 — sonnet/plan-exec (repo-grounded инвентаризация+guidance); P6.2 — opus/manual (GATED, first-party
дока обязательна ДО любого harness-действия). Фазы закрываются P6.1 → P6.2.
