# P0 — RAG-выжимка: нормы context-economy и телеметрия Claude Code

Дата верификации: 2026-07-12. Движок: perplexity-web (search). Потребители:
Inputs items P1.1, P2.1, P5.1, P5.3, P5.4; несущие маркеры `RAG:✅ 2026-07-12` плана.

## Запрос 1 — нормы стартового контекста

Запрос: «Claude Code 2026 best practices minimizing per-session context overhead:
SessionStart hooks additionalContext size, CLAUDE.md length limits, number of MCP
servers and tool definitions, skills/subagent descriptions in system prompt —
official guidance on context economy and startup budget».

Вердикты (источники: primeline.cc/blog/context-management ·
medium.com/@jpranav97 stop-wasting-tokens · xugj520.cn claude-code-architecture-guide ·
morphllm.com/claude-code-usage-limits):

- Стартовый бюджет: **3–7K ток** норм. проект, до ~10K сложный монорепо; >15K — аномалия.
- Hook additionalContext: **≤500–1500 ток**, только high-signal сводки, ссылки вместо контента.
- CLAUDE.md: **≤200 строк** (официальная рекомендация Anthropic), первые 200 строк <1K ток.
- Описание скилла: **10–30 ток**, 3–5 core-скиллов с авто-инвоком; редкие — без авто-инвока.
- MCP: 1–3 активных сервера; каждый сервер = десятки–сотни ток на tool-схемы резидентно.
- Rules — path-scoped (`paths:` frontmatter), не в always-on CLAUDE.md.

## Запрос 2 — телеметрия Claude Code (для P5.3/P5.4)

Запрос: «Claude Code 2026 telemetry and observability: OpenTelemetry support,
what metrics/events are exported, hooks JSON payloads, session transcript jsonl
fields — full list for per-session token analytics».

Вердикты (источники: code.claude.com/docs/en/monitoring-usage ·
claude-dev.tools/docs/jsonl-format):

- jsonl-транскрипты (`~/.claude/projects/<enc>/<sid>.jsonl`): per-turn `message.usage`
  (input/output/cache_creation/cache_read) — уже пишутся, основа P5.3.
- OTEL-метрики: `CLAUDE_CODE_ENABLE_TELEMETRY=1` + `OTEL_METRICS_EXPORTER=otlp` —
  счётчики токенов/стоимости по моделям, sessions, tool decisions; session.id по умолчанию;
  свои атрибуты через `OTEL_RESOURCE_ATTRIBUTES` (разрез по проектам).
- Enhanced traces (бета): `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` +
  `OTEL_TRACES_EXPORTER=otlp` — спаны per-LLM-вызов (токены, TTFT, retry),
  **per-хук** (hook_event, длительность, num_blocking), per-tool
  (`skill_name`/`file_path`/`full_command` при `OTEL_LOG_TOOL_DETAILS=1`),
  атрибуция субагентов (`agent_id`, `workflow.run_id`).
- Приватность: prompt-текст только при `OTEL_LOG_USER_PROMPTS=1`; сырые API-тела —
  `OTEL_LOG_RAW_API_BODIES` (thinking редактируется).

## Данные разведки сессий (локальные, не RAG)

Скрипт и сырьё: scratchpad-сессии 4af788f3 (`analyze_sessions.py`, `sessions_raw.json`).
Ключевые числа: медиана first_turn_overhead 10.7K (W24) → 31.9K (W28); скачок в W27
совпадает с e041862 (agent-router, 01.07); agelto max 139.7K; декомпозиция первого хода
agelto-сессии 9e70a918: skill_listing ~8.5K ток · digest ~2.6K ток · agent_listing ~1.7K ток ·
deferred_tools ~1.2K ток · system prompt/tool defs ~65K ток.
